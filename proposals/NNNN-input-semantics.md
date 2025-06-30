# HLSL shader semantics

* Proposal: [NNNN](http://NNNN-input-semantics.md)
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

They only carry meaning when used on:
  - an entry point parameter
  - entrypoint return value
  - a struct type used by an entry point parameter or return value.
All other uses are simply ignored.

When a semantic is applied to both a parameter/return value, and its type,
the parameter/return value semantic applies, and the type's semantics are
ignored.

Each scalar in the entrypoint must have a semantic attribute attached, either
directly or inherited from the parent struct type.

When a semantic applies to an array type, each element of the array
is considered to take one index space in the semantic.
When a semantic applies to a struct, each scalar field (recursively) takes
one index in the semantic.

Shader semantics on function return value are output semantics.
When applying to an entrypoint parameter, the `in`/`out`/`inout` qualifiers
will determine if this is an input or output semantic.

Each semantic is *usually* composed of two elements:
 - a case insensitive name
 - an index

Any semantic starting with the `SV_` prefix is considered to be a system
semantic. Some system semantics do not have indices, while other have. All
user semantics have an index (implicit or explicit).

The index can be either implicit (equal to 0), or explicit:

 - `Semantic`, Name = SEMANTIC, Index = 0
 - `SEMANTIC0`, Name = SEMANTIC, Index = 0
 - `semANtIC12`, Name = SEMANTIC, Index = 12


The HLSL language does not impose restriction on the indices except it has to
be a positive integer or zero. Target APIs can apply additional restrictions.
The same semantic (name+index) must only appear once on the inputs, and once
on the outputs.

Each stage has a fixed list of allowed system semantics for its
inputs or outputs. If user semantics are allowed as input or output semantics
depends on the shader stage being
targeted.

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

```
class HLSLSemanticAttr : HLSLAnnotationAttr;

def HLSLUnparsedSemantic : HLSLSemanticAttr {
  let Spellings = [];
  let Args = [];
  let Subjects = SubjectList<[ParmVar, Field, Function]>;
  let LangOpts = [HLSL];
  let Documentation = [InternalOnly];
}

def HLSLUserSemantic : HLSLSemanticAttr {
  let Spellings = [];
  let Args = [DefaultIntArgument<"Location", 0>, DefaultBoolArgument<"Implicit", 0>];
  let Subjects = SubjectList<[ParmVar, Field, Function]>;
  let LangOpts = [HLSL];
  let Documentation = [InternalOnly];
}

def HLSLSV_GroupThreadID: HLSLSemanticAttr {
  let Spellings = [];
```

During an attribute parsing, we first assign the `HLSLUnparsedSemantic` kind
to any HLSL semantic-like notation.

When, when this attribute kind is parsed, we rely on Sema to emit the correct
`HLSLUserSemanticAttr` or `HLSLSV_*Attr`, etc.

Sema will do stateless checks like:
  - Is this system semantic compatible with this shader stage?
  - Is this system semantic compatible with the type it's associated with?

We must also consider `MY_SEMANTIC0` to be equal to `MY_semantic`.
The solution is to modify the `ParseHLSLAnnotations` function to add a custom
attribute parsing function.

```cpp
struct ParsedSemantic {
  // The normalized name of the semantic without index.
  StringRef Name;
  // The index of the semantic. 0 if implicit.
  unsigned Index;
  // Was the index explicit in the name or not.
  bool Implicit;
};

Parser::ParsedSemantic Parser::ParseHLSLSemantic();
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

The proposal is to provide a sorted list of valid semantics in `CGHLSLRuntime`,
and then we can have a per-backend implementation for index assignment.

```cpp
struct SemanticIO {
  // The active semantic for this scalar/field.
  HLSLAnnotationAttr *Semantic;

  // Info about this field/scalar.
  DeclaratorDecl *Decl;
  llvm::Type *Type;

  // The loaded value in the wrapper for this scalar/field. Each target
  // must provide this value.
  llvm::Value *Value = nullptr;
};

Vector<SemanticIO> InputSemantics;
```

The pseudo code would be as follows

```python

  def emitEntryFunction():
    # Current emitEntryFunction code in CGHLSLRuntime.cpp.
    ...

    semantics = {}

    foreach (Parameter, ReturnValue) in FunctionDecl:
      if item is output:
        # output parameters.
        var = createLocalVar(item)
        semantics[item.semantic_name] = getPointerTo(var)
      elif item is byval:
        # Semantic structs passed as input.
        var = createLocalVar(item)
        loadSemanticRecursivelyToVariable(item, var)
        semantics[item.semantic_name] = getPointerTo(var)
      elif item is input:
        semantics[item.semantic_name] = loadSemanticRecursively(item)


    Args = [ semantics[x->semantic_name] for x in AllParameters ]
    call = createCall(MainFunction, Args)
    if not call->isVoid():
      StoreOutputSemanticRecursively(call, semantics)
```

The proposal is to let each target implement the logic in CGHLSLRuntime to
load the semantics, and set the `Value` field of the `SemanticIO` struct.
The order of the vector represents the flattening order.

Providing the full list should allow DXIL to easily implement packing rules.

At this stage, `CGHLSLRuntime` will have an ordered list of `SemanticIO`
structs. The order is from the first parameter/field to the last
parameter/field (DFS), and each will point to an `llvm::Value`.

The common code will then build the arguments list for the entrypoint call
using the provided `llvm::Value`. This is shared across targets.

The pseudo-code for this check should be:


At this point, we are guaranteed to have only valid and unique semantics, as
well as valid types.

