---
title: "[NNNN] - HLSL Intrinsic TableGen"
params:
  authors:
    - icohedron: Deric Cheung
  status: Under Consideration
---

## Introduction

This proposal introduces a TableGen-based system for generating HLSL
intrinsic function overload declarations and definitions. HLSL intrinsics
require many explicit overloads for each combination of element type (half,
float, int, etc.) and shape (scalar, vector, matrix). A single function
like `clamp` [needs 36 hand-written overloads for scalars and vectors
alone](https://github.com/llvm/llvm-project/blob/dd76cf68d392a6bcbdfefc2970a391486aa48825/clang/lib/Headers/hlsl/hlsl_alias_intrinsics.h#L614-L707).
The TableGen approach replaces these with compact declarative
definitions that are expanded by a backend into the required HLSL
declarations, significantly reducing the amount of hand-written code
in the HLSL intrinsic headers.

## Motivation

The HLSL intrinsic headers contain thousands of lines of repetitive
overload declarations. For example, the `and` function requires 40
lines of hand-written code to cover its scalar, vector, and matrix
overloads — all following an identical pattern of
`_HLSL_BUILTIN_ALIAS` followed by a function signature:

```hlsl
_HLSL_BUILTIN_ALIAS(__builtin_hlsl_and)
bool and(bool x, bool y);
_HLSL_BUILTIN_ALIAS(__builtin_hlsl_and)
bool2 and(bool2 x, bool2 y);
_HLSL_BUILTIN_ALIAS(__builtin_hlsl_and)
bool3 and(bool3 x, bool3 y);
_HLSL_BUILTIN_ALIAS(__builtin_hlsl_and)
bool4 and(bool4 x, bool4 y);

_HLSL_BUILTIN_ALIAS(__builtin_hlsl_and)
bool1x2 and(bool1x2 x, bool1x2 y);
_HLSL_BUILTIN_ALIAS(__builtin_hlsl_and)
bool1x3 and(bool1x3 x, bool1x3 y);
_HLSL_BUILTIN_ALIAS(__builtin_hlsl_and)
bool1x4 and(bool1x4 x, bool1x4 y);
_HLSL_BUILTIN_ALIAS(__builtin_hlsl_and)
bool2x1 and(bool2x1 x, bool2x1 y);
_HLSL_BUILTIN_ALIAS(__builtin_hlsl_and)
bool2x2 and(bool2x2 x, bool2x2 y);
_HLSL_BUILTIN_ALIAS(__builtin_hlsl_and)
bool2x3 and(bool2x3 x, bool2x3 y);
_HLSL_BUILTIN_ALIAS(__builtin_hlsl_and)
bool2x4 and(bool2x4 x, bool2x4 y);
// ... 9 more matrix overloads ...
_HLSL_BUILTIN_ALIAS(__builtin_hlsl_and)
bool4x4 and(bool4x4 x, bool4x4 y);
```

This pattern is repeated for each of the ~60 alias intrinsic functions.
A similar pattern applies to ~14 detail-wrapper intrinsics (inline
functions that forward to `__detail::*_impl` helpers) and a handful
of inline-body intrinsics (e.g., unsigned `abs` as a constexpr
identity). In all cases, every type × shape combination must be
written by hand. The repetition creates several problems:

1. **Maintenance burden.** Adding a new element type or shape to an
   intrinsic requires adding overloads by hand to every affected
   function. As matrix support is extended to more intrinsics, each
   one will need up to 15 additional overloads per element type —
   for a function like `clamp` that supports 9 element types, that
   means 135 new hand-written overloads.

2. **Inconsistency risk.** With thousands of similar declarations,
   it is easy to introduce subtle errors (wrong type, missing
   availability attribute, wrong builtin alias) that are hard to
   spot in review.

3. **16-bit availability complexity.** Half and 16-bit integer types
   require conditional availability attributes
   (`_HLSL_16BIT_AVAILABILITY` vs `_HLSL_AVAILABILITY`) and
   `#ifdef __HLSL_ENABLE_16_BIT` guards. Getting this right for
   every overload is tedious and error-prone.

4. **Template instantiation differs from overload resolution.** Some
   existing intrinsics use C++ templates to reduce repetition, but
   this changes call-site semantics — preventing implicit conversions,
   scalar-to-aggregate splats, and truncations that work with
   explicit overloads (see [C++ templates](#c-templates) in
   Alternatives considered).

A TableGen-based approach addresses all of these by capturing each
intrinsic's type and shape requirements declaratively, and generating
the correct explicit overloads — whether alias declarations, detail
function wrappers, or inline bodies — with proper availability
attributes and `#ifdef` guards automatically.

## Proposed solution and design

Define HLSL intrinsics declaratively in a TableGen file
(`HLSLIntrinsics.td`) and use a custom TableGen backend
(`HLSLEmitter`) to generate the overload declarations.
For instance, the `and` example in the motivation above becomes:

```tablegen
def hlsl_and : HLSLTwoArgBuiltin<"and", "__builtin_hlsl_and"> {
  let VaryingTypes = [BoolTy];
}
```

This 3-line definition generates all 19 overloads (1 scalar +
3 vector + 15 matrix) that previously required 40 lines of
hand-written code.

### The `HLSLBuiltin` class

Each intrinsic is defined as an `HLSLBuiltin` record that describes
**what** types it supports and **how** it maps to the underlying
implementation. The TableGen emitter reads these records and
generates the full set of explicit overloads.

The `HLSLBuiltin` class takes two positional parameters: `name` (the
HLSL function name) and `builtin` (the Clang builtin to alias, which
defaults to `""`). These populate the `Name` and `Builtin` fields
respectively. The remaining fields are set via `let` overrides:

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `Name` | `string` | *(positional, required)* | The HLSL function name (e.g., `"clamp"`). Populated by the first parameter. |
| `Builtin` | `string` | `""` *(positional)* | The Clang builtin to alias (e.g., `"__builtin_hlsl_elementwise_clamp"`). Populated by the second parameter. When set to a non-empty string, overloads are emitted with `_HLSL_BUILTIN_ALIAS`. Mutually exclusive with `DetailFunc` and `Body` if set to a non-empty string. |
| `Doc` | `string` | `""` | Doxygen comment emitted before the overloads. |
| `ReturnType` | `HLSLReturnType` | `Void` | How the return type is derived for each overload (see [Argument and return type descriptors](#argument-and-return-type-descriptors)). |
| `Args` | `list<HLSLArg>` | `[]` | Argument list. Each entry is a type descriptor. The length determines the argument count. |
| `VaryingTypes` | `list<HLSLType>` | `[]` | Element types to expand over. One overload set (scalar + vectors + matrices) is generated per type. |
| `ScalarVaryingType` | `bit` | `0` | Whether to generate scalar overloads. |
| `VaryingVecSizes` | `list<int>` | `[]` | Vector sizes to generate (e.g., `[2, 3, 4]`). |
| `VaryingMatDims` | `list<MatDim>` | `[]` | Matrix dimensions to generate (e.g., `AllMatDims`). Each `MatDim` has `Rows` and `Cols` fields. |
| `DetailFunc` | `string` | `""` | When set, generates an inline function that forwards to `__detail::DetailFunc(args...)`. Mutually exclusive with `Builtin` and `Body`. |
| `Body` | `string` | `""` | When set, generates an inline function with this literal body text. Mutually exclusive with `Builtin` and `DetailFunc`. |
| `ParamNames` | `list<string>` | `[]` | Custom parameter names for the arguments. When empty, inline functions use `p0`, `p1`, ... |
| `IsConstexpr` | `bit` | `0` | Emits `constexpr` instead of `inline` for inline functions. |
| `IsConvergent` | `bit` | `0` | Marks the function as convergent. |
| `Availability` | `ShaderModel` | `NoSM` | Minimum shader model version. When set, overloads are annotated with `_HLSL_AVAILABILITY`. |

The `Availability` field uses `ShaderModel` records:

```tablegen
class ShaderModel<int major, int minor> {
  int Major = major;
  int Minor = minor;
}

def NoSM  : ShaderModel<0, 0>;  // no availability annotation
def SM6_0 : ShaderModel<6, 0>;
def SM6_2 : ShaderModel<6, 2>;
def SM6_4 : ShaderModel<6, 4>;
```

A matrix dimension class and named records for each valid dimension
are also provided for filling out the `VaryingMatDims` field:

```tablegen
class MatDim<int rows, int cols> {
  int Rows = rows;
  int Cols = cols;
}

def Mat1x2 : MatDim<1, 2>;
def Mat1x3 : MatDim<1, 3>;
// ... Mat1x4, Mat2x1, ..., Mat4x4
```

| Group | Dimensions |
|-------|------------|
| `AllMatDims` | `Mat1x2` through `Mat4x4` (15 records, excluding 1×1) |


### Element types and type groups

Each HLSL scalar type is defined as an `HLSLType` record with flags
controlling 16-bit availability behavior:

| Record | HLSL type | `Is16Bit` | `IsConditionally16Bit` |
|--------|-----------|-----------|------------------------|
| `BoolTy` | `bool` | | |
| `HalfTy` | `half` | | ✓ |
| `FloatTy` | `float` | | |
| `DoubleTy` | `double` | | |
| `Int16Ty` | `int16_t` | ✓ | |
| `UInt16Ty` | `uint16_t` | ✓ | |
| `IntTy` | `int` | | |
| `UIntTy` | `uint` | | |
| `Int64Ty` | `int64_t` | | |
| `UInt64Ty` | `uint64_t` | | |
| `UInt32Ty` | `uint32_t` | | |

Commonly-used groups of types are provided as lists:

| Group | Types |
|-------|-------|
| `AllFloatTypes` | `half`, `float`, `double` |
| `SignedIntTypes` | `int16_t`, `int`, `int64_t` |
| `UnsignedIntTypes` | `uint16_t`, `uint`, `uint64_t` |
| `AllIntTypes` | `int16_t`, `uint16_t`, `int`, `uint`, `int64_t`, `uint64_t` |
| `SignedTypes` | `int16_t`, `half`, `int`, `float`, `int64_t`, `double` |
| `AllNumericTypes` | all integer and float types |
| `AllTypesWithBool` | `bool` + all numeric types |
| `NumericTypesNoDbl` | all numeric types except `double` |

### Overload expansion

An intrinsic like `clamp` supports many
types (`int`, `float`, `half`, ...) and many shapes (scalar, `vec2`,
`vec3`, `vec4`, and matrices). Rather than listing every combination
by hand, the definition uses `Varying` as a placeholder for the
return type and arguments. `VaryingTypes` specifies which element
types to expand over, and `ScalarVaryingType`, `VaryingVecSizes`,
and `VaryingMatDims` specify which shapes to generate. The emitter
then substitutes `Varying` with each type × shape combination to
produce the full set of overloads:

```tablegen
def hlsl_clamp : HLSLBuiltin<"clamp",
    "__builtin_hlsl_elementwise_clamp"> {
  let ReturnType = Varying;
  let Args = [Varying, Varying, Varying];
  let VaryingTypes = AllNumericTypes;
  let ScalarVaryingType = 1;
  let VaryingVecSizes = [2, 3, 4];
  let VaryingMatDims = AllMatDims;
}
```

This generates overloads across all numeric types, each
with scalar, vec2/3/4, and all 15 matrix shapes (1×2 through 4×4).

```hlsl
// clamp overloads
_HLSL_16BIT_AVAILABILITY(shadermodel, 6.2)
_HLSL_BUILTIN_ALIAS(__builtin_hlsl_elementwise_clamp)
half clamp(half, half, half);
_HLSL_16BIT_AVAILABILITY(shadermodel, 6.2)
_HLSL_BUILTIN_ALIAS(__builtin_hlsl_elementwise_clamp)
half2 clamp(half2, half2, half2);
// ... half3, half4 ...

#ifdef __HLSL_ENABLE_16_BIT
_HLSL_AVAILABILITY(shadermodel, 6.2)
_HLSL_BUILTIN_ALIAS(__builtin_hlsl_elementwise_clamp)
int16_t clamp(int16_t, int16_t, int16_t);
// ... int16_t2–4, uint16_t–uint16_t4 ...
#endif

_HLSL_BUILTIN_ALIAS(__builtin_hlsl_elementwise_clamp)
int clamp(int, int, int);
_HLSL_BUILTIN_ALIAS(__builtin_hlsl_elementwise_clamp)
int2 clamp(int2, int2, int2);
// ... int3, int4, uint–uint4, float–float4, int64_t–int64_t4, ...
// ... uint64_t–uint64_t4, double–double4 ...

// matrix overloads (for each type above)
_HLSL_BUILTIN_ALIAS(__builtin_hlsl_elementwise_clamp)
int1x2 clamp(int1x2, int1x2, int1x2);
_HLSL_BUILTIN_ALIAS(__builtin_hlsl_elementwise_clamp)
int1x3 clamp(int1x3, int1x3, int1x3);
// ... int1x4, int2x1, int2x2, ..., int4x4 ...
// ... same 15 matrix shapes for uint, float, double, int64_t, uint64_t ...
```

#### Common helper subclasses

Because the pattern of "all arguments and the return type share the
same type, with scalar + vector + matrix shapes" is so common, helper
subclasses are provided. For example, `HLSLThreeArgBuiltin` is
defined as:

```tablegen
class HLSLThreeArgBuiltin<string name, string builtin>
    : HLSLBuiltin<name, builtin> {
  let Args = [Varying, Varying, Varying];
  let ReturnType = Varying;
  let ScalarVaryingType = 1;
  let VaryingVecSizes = [2, 3, 4];
  let VaryingMatDims = AllMatDims;
}
```

`HLSLOneArgBuiltin` and `HLSLTwoArgBuiltin` follow the same pattern
with one and two arguments respectively. Similar helpers exist for
detail function and inline body modes (see
[Three generation modes](#three-generation-modes)):

```tablegen
class HLSLTwoArgDetail<string name, string detail> : HLSLBuiltin<name> {
  let DetailFunc = detail;
  let Args = [Varying, Varying];
  let ReturnType = Varying;
  let ScalarVaryingType = 1;
  let VaryingVecSizes = [2, 3, 4];
  let VaryingMatDims = AllMatDims;
}

class HLSLOneArgInlineBuiltin<string name> : HLSLBuiltin<name> {
  let Args = [Varying];
  let ReturnType = Varying;
  let ScalarVaryingType = 1;
  let VaryingVecSizes = [2, 3, 4];
  let VaryingMatDims = AllMatDims;
}
```

Using these helpers, the `clamp` definition above can be shortened to:

```tablegen
def hlsl_clamp : HLSLThreeArgBuiltin<"clamp",
    "__builtin_hlsl_elementwise_clamp"> {
  let VaryingTypes = AllNumericTypes;
}
```

### Argument and return type descriptors

Most intrinsics have
arguments and return types that directly follow the varying type —
e.g., `float3 clamp(float3, float3, float3)`. But some intrinsics
need arguments or return types that differ from the varying type in a
structured way. A set of type descriptor classes express these
relationships:

- `Varying` — directly uses the varying type.
- `VaryingElemType` — always the scalar element type regardless of
  shape. For example, `refract` takes a scalar `eta` parameter even
  when operating on vectors: `float3 refract(float3, float3, float)`.
- `VaryingShape<T>` — same shape as the varying type but with a
  fixed element type `T`. For example, `countbits` returns `uint3`
  for an `int3` input: `uint3 countbits(int3)`.
- `T` (an `HLSLType` record, e.g. `FloatTy`), `VectorType<T, N>` —
  fully fixed types that do not change across overloads.

For example, `refract` is defined as:

```tablegen
def hlsl_refract : HLSLBuiltin<"refract"> {
  let DetailFunc = "refract_impl";
  let VaryingTypes = [HalfTy, FloatTy];
  let Args = [Varying, Varying, VaryingElemType];
  let ReturnType = Varying;
  let ScalarVaryingType = 1;
  let VaryingVecSizes = [2, 3, 4];
}
```

The first two arguments and the return type use `Varying`, so they
follow the current type and shape (e.g., `float3`). The third
argument uses `VaryingElemType`, so it is always the scalar element
type (e.g., `float`) regardless of the vector size. This produces
overloads:

```c++
_HLSL_16BIT_AVAILABILITY(shadermodel, 6.2)
inline half refract(half p0, half p1, half p2) {
  return __detail::refract_impl(p0, p1, p2);
}
_HLSL_16BIT_AVAILABILITY(shadermodel, 6.2)
inline half2 refract(half2 p0, half2 p1, half p2) {
  return __detail::refract_impl(p0, p1, p2);
}
// ... half3, half4 ...
inline float refract(float p0, float p1, float p2) {
  return __detail::refract_impl(p0, p1, p2);
}
inline float2 refract(float2 p0, float2 p1, float p2) {
  return __detail::refract_impl(p0, p1, p2);
}
// ... float3, float4 ...
```

### Three generation modes

An `HLSLBuiltin` generates code in one of three modes:

1. **Alias mode** (`Builtin` is set) — emits `_HLSL_BUILTIN_ALIAS(builtin)`
   before each declaration. Used for intrinsics that map directly to
   a Clang builtin.

   ```tablegen
   def hlsl_ceil : HLSLOneArgBuiltin<"ceil", "__builtin_elementwise_ceil"> {
     let VaryingTypes = [HalfTy, FloatTy];
     let VaryingMatDims = [];
   }
   ```

   Generates:
   ```hlsl
   _HLSL_16BIT_AVAILABILITY(shadermodel, 6.2)
   _HLSL_BUILTIN_ALIAS(__builtin_elementwise_ceil)
   half ceil(half);
   _HLSL_16BIT_AVAILABILITY(shadermodel, 6.2)
   _HLSL_BUILTIN_ALIAS(__builtin_elementwise_ceil)
   half2 ceil(half2);
   // ... half3, half4 ...
   _HLSL_BUILTIN_ALIAS(__builtin_elementwise_ceil)
   float ceil(float);
   // ... float2, float3, float4 ...
   ```

2. **Detail function mode** (`DetailFunc` is set) — emits an inline
   function that forwards to a `__detail::*_impl` helper defined in
   `hlsl_intrinsic_helpers.h`.

   ```tablegen
   def hlsl_fmod : HLSLTwoArgDetail<"fmod", "fmod_impl"> {
     let ParamNames = ["X", "Y"];
     let VaryingTypes = [HalfTy, FloatTy];
     let VaryingMatDims = [];
   }
   ```

   Generates:
   ```hlsl
   _HLSL_16BIT_AVAILABILITY(shadermodel, 6.2)
   inline half fmod(half X, half Y) {
     return __detail::fmod_impl(X, Y);
   }
   _HLSL_16BIT_AVAILABILITY(shadermodel, 6.2)
   inline half2 fmod(half2 X, half2 Y) {
     return __detail::fmod_impl(X, Y);
   }
   // ... half3, half4 ...
   inline float fmod(float X, float Y) {
     return __detail::fmod_impl(X, Y);
   }
   // ... float2, float3, float4 ...
   ```

3. **Inline body mode** (`Body` is set) — emits an inline function
   with literal body text. Used for simple inline implementations
   like the unsigned `abs` identity.

   ```tablegen
   def hlsl_abs_unsigned : HLSLOneArgInlineBuiltin<"abs"> {
     let ParamNames = ["V"];
     let Body = "return V;";
     let IsConstexpr = 1;
     let VaryingTypes = UnsignedIntTypes;
     let VaryingMatDims = [];
   }
   ```

   Generates:
   ```hlsl
   constexpr uint16_t abs(uint16_t V) { return V; }
   constexpr uint abs(uint V) { return V; }
   constexpr uint64_t abs(uint64_t V) { return V; }
   // ... plus vector overloads
   ```

### Availability

The `Availability` field specifies a minimum shader model version for
an intrinsic. When set, every overload is annotated with
`_HLSL_AVAILABILITY(shadermodel, <major>.<minor>)`.

For example, `dot4add_i8packed` requires shader model 6.4:

```tablegen
def hlsl_dot4add_i8packed :
    HLSLBuiltin<"dot4add_i8packed", "__builtin_hlsl_dot4add_i8packed"> {
  let Args = [UIntTy, UIntTy, IntTy];
  let ReturnType = IntTy;
  let Availability = SM6_4;
}
```

Generates:

```hlsl
_HLSL_AVAILABILITY(shadermodel, 6.4)
_HLSL_BUILTIN_ALIAS(__builtin_hlsl_dot4add_i8packed)
int dot4add_i8packed(uint, uint, int);
```

#### 16-bit availability

Separately from per-intrinsic availability, when the emitter generates
overloads for a 16-bit type it automatically adds the appropriate
availability annotations based on flags on the `HLSLType` record:

- `Is16Bit` — the type is a true 16-bit type (e.g., `int16_t`,
  `uint16_t`). Overloads are wrapped in `#ifdef __HLSL_ENABLE_16_BIT`
  / `#endif` guards and emitted with
  `_HLSL_AVAILABILITY(shadermodel, 6.2)`.
- `IsConditionally16Bit` — the type has a 16-bit variant but is not always
  16-bit (e.g., `half`, which is a true 16-bit float only when
  `__HLSL_ENABLE_16_BIT` is defined, otherwise an alias for `float`).
  Overloads are emitted with
  `_HLSL_16BIT_AVAILABILITY(shadermodel, 6.2)`, which expands to an
  availability attribute only when `__HLSL_ENABLE_16_BIT` is defined
  and otherwise expands to nothing.

For either flag, if the intrinsic's own `Availability` is SM 6.2 or
later, `_HLSL_AVAILABILITY` is used instead since 16-bit support is
already implied.

This ensures that 16-bit overloads are only visible when the
target supports them, without the intrinsic author needing to
handle it manually. For example, `ceil` uses `[HalfTy, FloatTy]`
as its `VaryingTypes`. Since `HalfTy` has `IsConditionally16Bit`
set, the emitter automatically annotates the `half` overloads:

```hlsl
_HLSL_16BIT_AVAILABILITY(shadermodel, 6.2)
_HLSL_BUILTIN_ALIAS(__builtin_elementwise_ceil)
half ceil(half);
_HLSL_16BIT_AVAILABILITY(shadermodel, 6.2)
_HLSL_BUILTIN_ALIAS(__builtin_elementwise_ceil)
half2 ceil(half2);
// ... half3, half4 ...

// float overloads have no availability annotation
_HLSL_BUILTIN_ALIAS(__builtin_elementwise_ceil)
float ceil(float);
// ... float2, float3, float4 ...
```

### Generated file structure

The emitter produces two `.inc` files:

- `hlsl_intrinsics_gen.inc` — alias intrinsics
  (`_HLSL_BUILTIN_ALIAS` declarations)
- `hlsl_detail_intrinsics_gen.inc` — detail and inline-body
  intrinsics

These are included from `hlsl_intrinsics.h` with
`hlsl_intrinsic_helpers.h` (containing `__detail::*_impl` helper
functions) included between them to satisfy the dependency chain:
alias declarations → helpers (which reference alias-declared
functions) → detail intrinsics (which call helpers).

### Intrinsics that remain hand-written

Some intrinsics remain hand-written in `hlsl_intrinsics.h` because
they don't fit the "generate all overloads for a list of types"
pattern. These are:

- `asfloat`/`asint`/`asuint` — reinterpret the bits of a scalar or
  vector as a different element type, returning the same shape.
  These rely on a `sizeof` check in the template to reject types
  whose size doesn't match the target type (e.g., `asfloat(half)`
  must fail when native half is enabled because `sizeof(half) !=
  sizeof(float)`). With explicit overloads, the `half` argument
  would instead be implicitly promoted to `float` before the
  bit-cast, silently changing semantics.
- `asuint` (splitdouble variant) — uses `out` parameters
- `firstbithigh` — calls a helper templated on a `BitWidth`
  constant that differs per type group (16 for `int16_t`/`uint16_t`,
  32 for `int`/`uint`, 64 for `int64_t`/`uint64_t`). The detail
  function mechanism can only forward arguments to a helper, not
  pass type-dependent template arguments.
- `mul` — 9 cases mixing scalar, vector, and matrix operands where
  the return type depends on both argument kinds and matrices
  require compatible inner dimensions (e.g., `M×K * K×N → M×N`)
- `select` — the condition argument is always `bool`/`boolN` while
  the value arguments are templated over any type `T`

## Alternatives considered

### C++ templates

The initial approach attempted to replace the explicit overloads with
C++ function templates. While this worked for simple one-argument
functions, it failed because template argument
instantiation and function overload resolution behave fundamentally
differently in ways that change observable semantics:

**No implicit conversions across arguments.** With explicit
overloads, a call like `clamp(int_val, float_val, float_val)` is
rejected as ambiguous — the compiler lists all candidate overloads,
helping the user identify the mismatch. With a template
`T clamp(T, T, T)`, the same call is rejected with "deduced
conflicting types for parameter 'T'" — a less actionable diagnostic
that doesn't show which overloads were available. Both approaches
reject the call, but overloads produce more helpful errors.

**No implicit vector/matrix truncation.** With explicit overloads,
passing a `float4` to `cross(float3, float3)` truncates the
`float4` to a `float3` (with a warning). With a template
`vector<T,3> cross(vector<T,3>, vector<T,3>)`, the `float4` argument
cannot match `vector<T,3>` and the call is rejected.

**No implicit scalar-to-vector splat.** With explicit overloads,
`lerp(float3_val, float3_val, 0.5)` splats the scalar `0.5` into a
`float3`. With a template `T lerp(T, T, T)`, the compiler deduces
conflicting types (`float3` vs `float`) and rejects the call.

### Preprocessor macros

Overloads could be generated using X-macros or similar preprocessor
patterns. This would reduce line count but at the cost of
readability, debuggability, and IDE support. TableGen provides a
structured, type-safe approach with clear error messages and
integration with the existing LLVM build infrastructure.
