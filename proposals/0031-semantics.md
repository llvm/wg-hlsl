# HLSL shader semantics

* Proposal: [0031](0031-semantics.md)
* Author(s): [Nathan Gauër](https://github.com/Keenuts)
* Status: **Design In Progress**

## Introduction

HLSL shaders can read/write form/to the pipeline state using [semantics](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-semantics).
This proposal looks into how to implement semantics in Clang.

## Motivation

HLSL shader semantics are a core part of the shading language.

## Behavior

### HLSL

Shader semantics are used by the API to determine how to connect pipeline
data to the shader. HLSL has two kinds of semantics: System and User.
System semantics are linked to specific parts of the pipeline, while
user semantics are just a way for the user to link the output of a stage
to the input of another stage.

Shader semantic attributes can be applied to:
  - a function parameter
  - function return value
  - a struct field's declaration

The full semantic as used by the pipeline is composed of a case insensitive
name and an index.
When assigning a semantic attribute, a number may be appended to the name to
indicate the starting index for the semantic assignment.  If no number is
specified, the starting index is assumed to be `0`.
Any semantic starting with the `SV_` prefix is considered to be a system
semantic.

Examples:
 - `SEMANTIC0`, Name = SEMANTIC, Index = 0, user semantic
 - `Semantic`, Name = SEMANTIC, Index = 0, user semantic
 - `semANtIC12`, Name = SEMANTIC, Index = 12, user semantic
 - `SV_Position`, Name = SV_POSITION, Index = 0, system semantic
 - `SV_POSITION2`, Name = SV_POSITION, Index = 2, system semantic

The HLSL language does not impose restriction on the indices except it has to
be a positive integer or zero. Target APIs can apply additional restrictions.
The same semantic (name+index) must only appear once on the inputs, and once
on the outputs.

Semantic attributes only carry meaning when used on:
  - an entry point parameter
  - an entry point function or the return value
  - fields of a struct used by an entry point parameter or return value.
All other uses are simply ignored.

A semantic attribute applied to a field, parameter, or function declaration
will override all inner semantics on any fields contained in that
declaration's type.
When a semantic is overriden, the compiler shall emit a warning stating
which semantic was overriden by the enclosing type or the function.

For entry functions, every parameter and non-void return value must have an
assigned semantic. This semantic must come from either:
 - a semantic attribute on the parameter
 - a semantic attribute on all structure fields in the type's declaration.
 - for return values, a semantic attribute on the function

Shader semantics on function return value are output semantics.
When applying to an entrypoint parameter, the `in`/`out`/`inout` qualifiers
will determine if this is an input or output semantic.

Each stage has a fixed list of allowed system semantics for its
inputs or outputs. If user semantics are allowed as input or output semantics
depends on the shader stage being targeted.

The semantic index correspond to a storage "row" in the pipeline.
Each "row" can store at most a 4-component 32bit numeric value.
This implies a struct with multiple `float4` fields will be stored over
multiple "rows", hence will span over multiple semantic indices.

Example:
 - `float   s : MY_SEMANTIC` takes one row, implicitly set to `0`.
 - `float   s : MY_SEMANTIC0` takes one row, explicitly set to `0`.
 - `float4  s : MY_SEMANTIC0` takes one row, explicitly set to `0`.
 - `double4 s : MY_SEMANTIC0` takes two rows, `0` and `1`.

- Struct fields, arrays and matrices may require more than one "row" depending
  on their dimensions.
- Each array element, struct field, or matrix row starts on a new "row",
  there is no packing.
- Indices are assigned from the first element/field to the last, recursively
  in a depth-first order.
- An array of size N with elements taking M rows will take a total of
  N x M rows.
- Each semantic+index pair can appear once on the inputs, and once on the
  outputs.

Example:
 - `float arr[2] : MY_SEM` takes 2 rows, `0` and `1`.
   Even if a row could store multiple floats, each array element starts on a
   new row.

 - `double3 arr[2] : MY_SEM1` takes 4 rows, `1`, `2`, `3` and `4`.
   Each double3 require 2 rows, and thus the array requires 4 rows.
   `arr[0]` will take `1` and `2`, and `arr[1]` `3`, `4`.

Examples:

```hlsl
float main(float a : A) : B {}
// a : A0
// main() : B0
```

```hlsl
struct S {
  int f1 : A;
  int f2 : B;
};

void main(S s) {}
// s.f1 : A0
// s.f2 : B0
```

```hlsl
struct S {
  int f1;
  int f2;
};

void main(S s : A) {}
// s.f1 : A0
// s.f2 : A1
```

```hlsl
struct S {
  int f1 : B0;
  int f2 : C0;
};

void main(S s : A) {}
// s.f1 : A0
// s.f2 : A1
```

```hlsl
struct C {
  int c1;
  int c2;
};

struct S {
  int f1;
  C   f2;
  int f3;
};

void main(S s : A) {}
// s.f1    : A0
// s.f2.c1 : A1
// s.f2.c2 : A2
// s.f3    : A3
```

```hlsl
struct C {
  int c1;
  int c2;
};

struct S {
  int f1[2];
  C   f2;
  int f3;
};

void main(S s : A) {}
// s.f1[0]    : A0
// index takes by the second element in s.f1[]
// s.f2.c1    : A2
// s.f2.c2    : A3
// s.f3       : A4
```

```hlsl
void main(int a : A0, int b : A) {}
// Illegal: Semantic A0 is used twice (A0 and A, implicit A0).
```

```hlsl
struct S {
  int f1 : A0;
};

void main(S s, int b : A0) {}
// Illegal: A0 is used twice, S.f1 and b.
```

```hlsl
struct S {
  int f1 : A0;
};

void main(S s : A1, int b : A0) {}
// s.f1 : A1, b : A0, this is legal.
```

```hlsl
struct S {
  int f1[2] : A0;
};

void main(S s, int b : A1) {}
// Illegal: s.f1[] is an array of 2 elements. Semantic is A0, but A1 is taken
// by the second element. Meaning there is a semantic overlap for A1.
```

```hlsl
void main(float4 a : POSITION0, out float4 b : POSITION0);
// a : POSITION0
// b : POSITION 0
// Legal: The semantic appears only once per input, and once per output.
```

### SPIR-V

On the SPIR-V side, user semantics are translated into `Location`
decorated `Input` or `Output` variables. The `Location` decoration takes an
index.
System semantics are either translated to `Location` or `BuiltIn` decorated
variables depending on the stage and semantic.

In the example above, there are no system semantics, meaning every
parameter would get a `Location` decorated variable associated.
Each scalar field/parameter is associated with a unique index starting at 0,
from the first parameter's field to the last parameter's field.
Each scalar takes one index, and arrays of size N takes N indices.
The semantic index does not impact the Location assignment.
Indices are independent between `Input` and `Output` semantics.

Example:

```hlsl
```hlsl
struct S {
  int f1[2] : A5;
};

void main(S s, out int c : A2, int b : A0, out int d : A0) {}
// s.f1 : A5 -> Location 0
// b    : A0 -> Location 2
// c    : A2 -> Location 0
// d    : A0 -> Location 1
// Semantic index does not contribute, only the parameter ordering does.
// Input and Outputs are sorted independently.
```

It is also possible to explicitly set the index, using the
`[[vk::location(/* Index */)]]` attribute. \
Mixing implicit and explicit location assignment is **not legal**.
Hence interaction between both mechanism is out of scope.

### DXIL

On the DXIL side, some system semantics are translated to builtin function
calls. But most are visible along user semantics in the `input signature`.

To pass data between stages, DirectX provides a fixed list of <4 x 32bit>
registers. E.g: 32 x <4 x 32 bit> for VS in D3D11.

The input signature assigns to each semantic a `Name`, `Index`, `Mask`,
`Register`, `SysValue`, and `Format`.

- `Name`: the semantic attribute name.
- `Index`: used to differentiate two inputs sharing the same `Name`.
- `Register`: determines which 16-byte register the value shall be read from.
- `Mask`:what 32-bit part is used for this value, e.g: `xyz` or `x`.
- `Format`: how to interpret the data, e.g. `float` or `int`.
- `SysValue`: `NONE` for user semantic, a known string for system semantics.

Unlike in SPIR-V, the `Register` and `Mask` cannot be simply deduced from the
iteration order. Those value depends on the [packing rules](https://github.com/Microsoft/DirectXShaderCompiler/blob/main/docs/DXIL.rst#signature-packing)
of the inputs.

## Proposal

SPIR-V and DXIL semantic lowering is very different. SPIR-V respects the
parameters/field order, while DXIL packs by following an extensive set of
rules. The System vs User semantics handling is also divergent.

This means we will be able to share the Sema checks, but will have to build
two distinct paths during codegen.

Also, the validity of the semantic attribute depends on its usage, meaning
we to facilitate code-reuse, some validation will have to be deferred to
CodeGen.

### Parser

Clang has a built-in mechanism for attribute parsing using a `.td` file.
But this requires enumerating the list of known semantics, which is not
possible for user semantics.

The attribute `.td` file must be changed to allow syntax-free semantics
to be parsed.
**NOTE**: All Spellings will be removed on already checked-in semantics.

```python
class HLSLSemanticAttr<bit Indexable> : HLSLAnnotationAttr {
  # SV_GroupID for ex cannot be indexed.
  bit SemanticIndexable = Indexable;
  # The index and wether it is explicit of not, ex: `USER0` vs `USER`.
  int SemanticIndex = 0;
  bit SemanticExplicitIndex = 0;

  let Spellings = [];
  let Subjects = SubjectList<[ParmVar, Field, Function]>;
  let LangOpts = [HLSL];
}

# This is is used by the first parsing stage: all semantics are initially
# set to HLSLUnparsedSemantic. Sema will then convert them to the final
# form.
def HLSLUnparsedSemantic : HLSLAnnotationAttr {
  let Spellings = [];
  let Args = [DefaultIntArgument<"Index", 0>,
              DefaultBoolArgument<"ExplicitIndex", 0>];
  let Subjects = SubjectList<[ParmVar, Field, Function]>;
  let LangOpts = [HLSL];
  let Documentation = [InternalOnly];
}

# User semantics will use this class.
def HLSLUserSemantic : HLSLSemanticAttr</* Indexable= */ 1> {
  let Documentation = [HLSLUserSemanticDocs];
}

# Known system semantics will have their own class with documentation.
# Note: here indexable is set to false.
def HLSLSV_GroupThreadID: HLSLSemanticAttr</* Indexable= */ 0> {
  let Documentation = [HLSLSV_GroupThreadIDDocs];
}
```

During an attribute parsing, we first assign the `HLSLUnparsedSemantic` kind
to any HLSL semantic-like notation.

When, when this attribute kind is parsed, we rely on Sema to emit the correct
`HLSLUserSemanticAttr` or `HLSLSV_*Attr`, etc.

Sema will do stateless checks like:
  - Is this system semantic compatible with this shader stage?
  - Is this system semantic compatible with the type it's associated with?
  - Is this system semantic indexable if an explicit index is used?

We must also consider `MY_SEMANTIC0` to be equal to `MY_semantic`.
The solution is to modify the `ParseHLSLAnnotations` function to add a custom
attribute parsing function.

The base-class `HLSLSemanticAttr` will expose two methods. During parsing,
the index is parsed from the name, and stored in each attribute.
The `SemanticExplicitIndex` is a bit useful for reflection and variable
name regeneration.

```cpp
  bool isSemanticIndexable() const;
  unsigned getSemanticIndex() const;
```

### Sema

Sema check is only stateless, and done during parsing.
The parser first emits an `HLSLUnparsedSemantic` attribute, which is passed
down to Sema.
Sema goal is to:
 - convert this class into a valid semantic class like `HLSLUserSemantic` or `HLSLSV_*`.
 - check shader stage compatibility with the system semantic.
 - check type compability with the system semantic.

At this stage, we have either `HLSLUserSemanticAttr` attributes, or known
compatible `HLSLSV_*Attr` attributes.
All non-converted `HLSLUnparsedSemantic` would have raised a diagnostic to
say `unknown HLSL system semantic X`.

No further checking is done as we must wait for codegen to move forward.

### CodeGen

DXIL and SPIR-V codegen will be very different, but the flattening/inheritance
bit can be shared.

The proposal is to have the whole semantic inheritance & validation shared,
and at the very end allow each target to emit the BuiltIn/Location codegen.


The pseudo code for the `emitEntryFunction` would be as follows:

```python

  def emitEntryFunction():
    # Current emitEntryFunction code in CGHLSLRuntime.cpp.
    ...

    args = []
    outputs = []

    foreach item in FunctionDecl.GetParamDecl():
      if item is sret_output:
        # Struct return values are using sret mechanism.
        var = createLocalVar(item.type)
        outputs.append({ item, var })
      elif item is byval_input:
        # Semantic structs passed as input.
        var = createLocalVar(item)
        value = loadSemanticRecursively(item, var)
        store(value, var)
        args.append(var.getPointer())
      elif item is input:
        # Values passed by copy
        args.append(loadSemanticRecursively(item))

    call_return_value = createCall(MainFunction, args)

    if not call->isVoid():
      output.append(FunctionDecl, call_return_value)

    for [decl, item] in outputs:
      value = load(item)
      storeSemanticRecusively(decl, value)
```

In this code, two main functions are to write:
 - `storeSemanticRecursively`
 - `loadSemanticRecursively`

Both will be quite similar, since both follow the same semantic
indexing/inheritance rules.

Pseudo code would be:

```python

def loadSemanticRecursively(decl, appliedSemantic = None):
  if (decl->isStruct())
    return loadSemanticStructRecurively()
  return loadSemanticScalarRecursively()

def loadSemanticStructRecurively(decl, &appliedSemantic)

  if appliedSemantic is None:
    appliedSemantic = decl->getSemantic()

  output = createEmptyStruct(decl->getType())
  for field in decl->structDecl():
    tmp = copy(appliedSemantic)
    val = loadSemanticRecursively(decl, tmp)
    output.insert(val, field.index)
  return output

def loadSemanticScalarRecursively(decl, &appliedSemantic):
  if appliedSemantic is None:
    appliedSemantic = decl->getSemantic()

  if appliedSemantic is None:
    raise ("semantic is required")

  if appliedSemantic->isUserSemantic():
    return emitUserSemanticLoad(decl, appliedSemantic)
  return emitSystemSemanticLoad(decl, appliedSemantic)

def emitSystemSemanticLoad(decl, &appliedSemantic):
  if appliedSemantic == SV_Position:
    # For SPIR-V for ex, logic is the same as user semantics.
    return emitUserSemanticLoad(decl, appliedSemantic)

  # But compute semantics based on builtins are different.
  if not this->ActiveInputSemantic.insert(appliedSemantic.Name):
    raise "duplicate semantic"

  if appliedSemantic == SV_GroupID:
    return emitSystemSemanticLoad_TARGET(decl, appliedSemantic)

  raise "Unknown system semantic"

def emitUserSemanticLoad(decl, &appliedSemantic):
  Length = decl->isArray() ? decl->getArraySize() : 1

  # Mark each index as busy. Some system semantics also require this,
  # the example above shows the compute semantic which has no index.
  for I in Length:
    SemanticName = appliedSemantic.SemanticName + I
    if not this->ActiveInputSemantic.insert(semanticName):
      raise "Duplicate semantic index"
    appliedSemantic.Index += 1

  # For SPIR-V, emit a global with a Location ID.
  return emitUserSemanticLoad_TARGET(decl, appliedSemantic)

def emitSystemSemanticLoad_TARGET(decl, &appliedSemantic):
  # Each target will emit the required code. This lives in CGHLSLRuntime,
  # meaning we can have state to determine packing rules, etc.

```

The proposal is to let each target implement the logic in CGHLSLRuntime to
load the semantics after all checks. What we expect is to get a single
value with the input semantic loaded.
For store, same scenario: the target-specific code will take an `llvm::Value`
with a non-aggregate value, and will have to store it to a semantic.
Index collision, semantic inheritance and invalid system semantics are handled
by the shared code.

A demo branch can be found here:
https://github.com/Keenuts/llvm-project/tree/hlsl-semantics

