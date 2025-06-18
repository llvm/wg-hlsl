# Input semantics

* Proposal: [NNNN](http://NNNN-input-semantics.md)
* Author(s): [Nathan Gauër](https://github.com/Keenuts)
* Status: **Design In Progress**

## Introduction

HLSL shaders can read form the pipeline state using [semantics](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-semantics).
This proposal looks into how to implement input semantics in Clang.
Output semantics are out of scope of this proposal, but some parts will be
similar.

## Motivation

HLSL input semantics are a core part of the shading language.

## Behavior

### HLSL

Input semantics are used by the API to determine how to connect pipeline
data to the shader.

Input semantic attributes can be applied to a function parameter, or a struct
field's declaration. They only carry meaning when used on an entry point
parameter, or a struct type used by one of the entry point parameters.
All other uses are simply ignored.

HLSL has two kinds of semantics: System and User.
System semantics are linked to specific parts of the pipeline, while
user semantics are just a way for the user to link the output of a stage
to the input of another stage.

When the semantic attribute is applied to a struct (type or value), it applies
recursively to each inner fields, shadowing any other semantic.

Each scalar in the entrypoint must have a semantic attribute attached, either
directly or inherited from the parent struct type.

Example:

```hlsl
struct B {
  int b1 : SB1;
  int b2 : SB2;
};

struct C {
  int c1 : SC1;
  int c2 : SC2;
};

struct D {
  int d1;
};

struct E {
  int e1 : EC;
  int e2 : EC;
};

struct F {
  int f1 : FC;
  int f2 : FC;
};

[[shader("pixel")]]
void main(float a : SA, B b : SB, C c, D d, E e, F f : SF) { }
```

In this example:
- `a` is linked to the semantic `SA`.
- `b.b1` and `b.b2` are linked to the semantic `SB` because `SB` shadows the
  semantics attached to each field.
- `c.c1` has the semantic `SC1`, and `c.c2` the semantic `SC2`.
- `d.d1`, hence `d`, is illegal: no semantic is attached to `d.d1`.
- `e.e1` and `e.e2` are invalid: `EC` usage is duplicated without being inherited.
- `f.f1` and `f.f2` semantic is `SF`, shadowing the duplicated `FC` semantic.

**Note**: HLSL forbids explicit **non-shadowed** semantic duplication. In this
sample, the parameter `e` uses `E`, which explicitly declares two fields with
the same semantic. This is illegal. \
`b` has the semantic `SB` applied on the whole struct. Meaning all its fields
share the same semantic `SB`. This is legal because the duplication comes
from inheritance.
Lastly, `f` explicitly duplicates the semantic `FC`. But because those are
shadowed by the semantic `SF`, this is valid HLSL.

**Note**: Implicit semantic duplication is allowed for user semantics, but
always forbidden for system semantics.

### SPIR-V

On the SPIR-V side, user semantics are translated into `Location`
decorated `Input` variables. The `Location` decoration takes an index.
System semantics are either translated to `Location` decorated `Input`
variables, or `BuiltIn` decorated `Input` variables.

In the example above, there are no system semantics, meaning every
parameter would get a `Location` decorated variable associated.
Each scalar field/parameter is associated with a unique index starting at 0,
from the first parameter's field to the last parameter's field.

In the sample above:

- `a` would have the `Location 0`.
- `b.b1` would have the `Location 1`.
- `b.b2` would have the `Location 2`.
- `c.c1` would have the `Location 3`.
- ...

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

### Sema

Type check for semantics is currently handled in `SemaDeclAttr.cpp`. \
Iteration is done on each declaration, and if a semantic attribute is present,
the type is checked.
Each declaration being handled independently, this method does not support
inherited/shadowed semantic attributes.

Sema checks are divided into three parts:
 - check for type compatibility between the variable and the semantic.
 - check for semantic duplication.
 - check for invalid system semantic usage depending on shader stage.

Proposition is to remove the type validation from the `SemaDeclAttr` and
move it later into SemaHLSL, with the other checks.
Idea is we need to have the inheritance rules to check types, so we should
avoid duplicating this logic in two places.

The pseudo-code for this check should be:

```cpp
  void checkSemantic(std::unordered_set<HLSLAnnotationAttr> &UsedSemantics,
                DeclaratorDecl *Decl,
                HLSLAnnotationAttr *InheritedSemantic = nullptr) {

    HLSLAnnotationAttr *Semantic = InheritedSemantic ? InheritedSemantic : Decl->get<HLSLAnnotationAttr>();
    RecordDecl *RD = dyn_cast<RecordDecl>(Decl);

    // Case 1: type is a scalar, and we have a semantic. End case.
    if (Semantic && !RD) {
      if (UsedSemantics.contains(Semantic) && !InheritedSemantic)
        Fail("Explicit semantic duplication", Decl->getLocation())

      UsedSemantics.insert(Semantic)
      diagnoseSemanticType(Decl, Semantic);
      diagnoseSemanticEnvironment(Decl, Context.ShaderEnv);
      return;
    }

    // Case 2: type is scalar, but we have no semantic: error
    if (!RD)
      Fail("Missing semantic", Decl->getLocation());

    // Case 3: it's a struct. Simply recurse, optionnally inherit semantic.
    if (RecordDecl *RD = dyn_cast<RecordDecl>(Decl)) {
      for (FieldDecl *FD : Decl->asRecordDecl()->getFields())
        checkSemantic(UsedSemantics, FD, Semantic);
    }
  }

  ...

  std::unordered_set<clang::HLSLAnnotationAttr> UsedSemantics;
  for (ParmVarDecl Decl : entrypoint->getParams()) {
    checkSemantic(UsedSemantics, Decl, /* InheritedSemantic= */ nullptr);
  }
```

At this point, we are guaranteed to have only valid and unique semantics, as
well as valid types.

### CodeGen

DXIL and SPIR-V codegen will be very different, but the flattening/inheritance
bit can be shared.

The proposal is to provide a sorted list in `CGHLSLRuntime`:

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

The proposal is to let each target implement the logic in CGHLSLRuntime to
load the semantics, and set the `Value` field of the `SemanticIO` struct.
The order of the vector represents the flattening order.

Providing the full list should allow DXIL to easily implement packing rules.

At this stage, `CGHLSLRuntime` will have an ordered list of `SemanticIO`
structs. The order is from the first parameter/field to the last
parameter/field (DFS), and each will point to an `llvm::Value`.

The common code will then build the arguments list for the entrypoint call
using the provided `llvm::Value`. This is shared across targets.
