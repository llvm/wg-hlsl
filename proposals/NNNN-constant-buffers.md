
# Constant buffers

* Proposal: [NNNN](NNNN-constant-buffers.md)
* Author(s): [Helena Kotas](https://github.com/hekota)
* Status: **Design In Progress**

## Introduction

Shader inputs usually include a number of constants which are stored in one or
more buffer resources in memory with specific packing rules. These resources can
be organized into two types of buffers: constant buffers and texture buffers.
This document describes design decisions related to constant buffers.

Constant buffers load from a constant buffer views (CBVs) and binds to registers
`b`.

There are three ways to declare a constant buffer in HLSL.

### `cbuffer` Declaration Block

A constant buffer can be declared using the `cbuffer` keyword. This looks very
much like a structure declaration in C with the addition of `register` and
`packoffset` keywords for manually assigning binding register or packing info.
For example:

```c++
cbuffer MyConstant : register(b1)  {
  float4 F;
}
```

Variables declared within the `cbuffer` scope can be accessed anywhere in a
shader by directly using the variable name (`F`) without referencing the name of
the constant buffer. Note that the name of the constant buffer is not a
recognized identifier and does not actually have to be unique.

### Default Constant Buffer `$Globals`

Any variable declaration in global scope that is not static and is not a
resource is implicitly added to a default constant buffer named `$Global`. That
means a global scope declaration like this:

```c++
float4 F;
```
is equivalent to

```c++
cbuffer $Globals {
  float4 F;
}
```

### `ConstantBuffer` Resource Class

Third way of declaring constant buffers is by using the `ConstantBuffer` class:

```c++
struct MyConstants {
  float4 F;
};

ConstantBuffer<MyConstants> CB;
```
 
In this case the buffer variables are referenced as if `CB` was of type
`MyConstants`. In other words, the float value in `MyConstants` struct is
referenced as `CB.F`.

## Motivation

We need to support constant buffers in Clang as they are a fundamental part of
the HLSL language. 

## Proposed Solution

### `hlsl_constant` address space

Constant buffer views (CBV) will be treated as a storage class with a new
address space `hlsl_constant` with value `2` for DXIL. Constant buffer elements
will be generated as global variables in `hlsl_constant` address space. Later on
in the backend there will be a pass that will collects all `addrspace(2)`
globals and loads from this address space and replace them with constant buffer
load intrinsics off a CBV handle.

### Parsing of `cbuffer` Declaration

In Clang frontend the `cbuffer` declaration will be parsed into a new AST node
 `HLSLBufferDecl`. This class will be based on `NameDecl` and `DeclContext`.

Variable declarations inside the `cbuffer` context will be children of this new
AST node and will have `hlsl_constant` address space.

If a variable declaration specifies a `packoffset`, this information will be
parsed into an `HLSLPackOffsetAttr` attribute and applied to the variable
declaration. See [packoffset attribute](0003-packoffset.md).

In order to make the variables declared in `cbuffer` scope exposed into global
scope we can take advantage of `DeclContext::isTransparentContext` method and
overload it to return true for `HLSLBufferDecl`. This is the same way variables
declared in `export` declaration context are exposed at the global scope.

### Layout Structure

The `cbuffer` block can contain any declaration that can occur at a global
scope, but not all of the declarations correspond to data in the CBV and
contribute to the buffer layout. As part of the semantic analysis the
declarations in `cbuffer` scope will be processed into a layout struct that will
represent the actual content of the constant buffer.

The layout struct will contain all declaration from the `cbuffer` block except:
- static variable declarations
- resource classes
- empty structs
- zero-sized arrays
- any non-variable declarations (functions, classes, ...)

If the constant buffer includes a struct variable, this struct it will also need
to be inspected and transformed into a new layout struct if it contains any of
the undesired declarations above.

For example for this `cbuffer` declaration:

```
struct Something {
  int a;
  float f[0];   // zero-sized array
};

cbuffer CB {
    float x;
    RWBuffer<float> buf;   // resource class
    Something s;           // embedded struct
    static float y;        // static variable
}
```

The buffer layout struct will look like this:
```
  struct __layout_Something {
      int a;
  };

  struct __layout_CB {
      float x;
      __layout_Something s;
  };
```

The layout struct for the constant buffer will be defined in the
`HLSLBufferDecl` declaration context and is going to be the last `CXXRecordDecl`
child of `HLSLBufferDecl`.

Layout structs for user defined structs will be added to the same declaration
context as the original struct (to the same namespace).

### Default Constant Buffer

 If there is any variable declaration at global scope that is not static or a
 resource the semantic analysis will create an implicit instance of
 `HLSLBufferDecl` named `$Globals` to represent the default constant buffer.
 This implicit `HLSLBufferDecl` instance will be used to store references to all
 variable declarations that belong to the default constant buffer. It will also
 be used as the declaration context for the buffer layout structure.

### `ConstantBuffer` Declaration

`ConstantBuffer<T>` is effectively an alias for type `T` in `hlsl_constant`
address space. If the `hlsl_constant` address space would be spellable it could
be defined as:

```
template <typename T> using ConstantBuffer = hlsl_constant T;
```

Definition of `ConstantBuffer` equivalent to the statement above will be added
to the `HLSLExternalSemaSource`.

Treating `ConstantBuffer` as an alias of `T` takes care the member access issue
- the `.` access refers directly to members of `T`, and global variables
declared using the `ConstantBuffer` syntax will be have the `hlsl_constant`
address space.

If `ConstantBuffer` allowed `T` to include only types allowed in CBV this is all
that would be needed to make `ConstantBuffer` work. Unfortunately DXC allows `T`
to have resources and or empty types, which means a layout struct might need to
created for `T`. For this reason we are most likely going to need to handle this
in a similar way as the default constant buffer by creating an implicit
`HLSLBufferDecl` that will reference the `ConstantBuffer` global variable and
hold the buffer layout struct definition.

### Lowering Constant Buffer Resources to LLVM IR

For each constant buffer the Clang codegen will create a global variable in
default address space. The type of the global will be `target("dx.CBuffer",
...)`. This global variable will be used for the resource handle initialization
and will be eventually removed. The target type will include 1 parameters - the
buffer layout structure.

For example this `cbuffer`:
```
cbuffer MyConstants {
  float2 a;
  int c;
}
```
would be translated a global variable with the following target type:
```
%class.__layout_MyConstants = type { <2 x float>, i32 }
@MyConstants.cb = global target("dx.CBuffer", %class.__layout_MyConstants)
```

### Lowering Accesses to Individual Constants to LLVM IR

For explicit `HLSLBufferDecl`s declarations (`cbuffer` syntax) Clang codegen
will create global variables for all of its variable declarations. Since the
declaration are already using the `hlsl_constant` address space the global
variables will be declared in this address space as well.

For implicit `HLSLBufferDecl`s declarations (`$Globals` and possibly
`ConstantBuffer<T>` syntax) the declarations already exist at the global scope
in the `hlsl_constant` address space, no changes should be needed here.

Accesses to these global constants will be translated to `load` instruction from
a pointer in `addrspace(2)`. These will be later on collected in an pass
`DXILConstantAccess` and replaced with load operations using a constant buffer
resource handle.

In order for the `DXILConstantAccess` pass to generate generate the correct CBV
load instructions it is going to need additinal information, such as which
constants belong to which constant buffer, and layout of the buffer and any
embedded structs. Codegen will generate this information as metadata. The exact
way the metadata will look like is TBD.

### DXIL Lowering

A new pass `DXILConstantAccess` will use the constant buffer information from
the metadata, the buffer global variables and its handle types
`target("dx.CBuffer", ...)`, and it will translate all `load` instructions in
`addrspace(2)` to the constant buffer DXIL ops.

It is an open question whether this pass should be translating the constant
accesses to `llvm.dx.cbufferBufferLoad` instructions which would later need to
be lowered to `cbufferLoadLegacy` ops, or whether it should generate the
`cbufferLoadLegacy` ops directly.

Similar transformation pass is going to be needed for SPIR-V target and if
possible we should share code related to this.

### Handle initialization

Clang codegen will constant buffer handle initialization the same way as it does
with other resource classes like raw buffers or structured buffers.

## Detailed design

*TBD*

## Alternatives considered

- Generate access to `cbuffer` varibles as memory accesses with the offset based
  on cbuffer layout and treat cbuffers as one big type-less memory blob in LLVM
  IR.
  - There is a concern that losing the type information could lead to
    unnecessary copying of values.

- Generate `llvm.dx.cbufferBufferLoad` instruction in Clang codegen whenever a
  global constant variable is accesses.
  - This would require intercepting all emits of `load` instructions in the
  codegen and might turn out quite messy.

## Open issues

## Links

[Shader
Constants](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-constants)<br/>
[Packing Rules for Constant
Variables](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-packing-rules)<br/>
[HLSL Constant Buffer Layout
Visualizer](https://maraneshi.github.io/HLSL-ConstantBufferLayoutVisualizer)<br/>
[`packoffset` Attribute](0003-packoffset.md)</br>

## Open issues
-- Nested `cbuffer` declarations
-- Format of the constant buffer metadata emitted by codegen
-- Should the `DXILConstantAccess` pass generate `cbufferLoadLegacy` ops directly?

## Acknowledgments (Optional)

