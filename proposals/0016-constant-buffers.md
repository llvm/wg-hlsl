
# Constant buffers

* Proposal: [16](0015-constant-buffers.md)
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
- static or groupshared variable declarations
- resource classes
- empty structs
- zero-sized arrays
- any non-variable declarations (functions, classes, ...)

If the constant buffer includes a struct variable, it will also need to be
inspected and transformed into a new layout struct if it contains any of the
undesired declarations above.

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
`HLSLBufferDecl` declaration contex. If a layout struct needs to be created for
a user defined struct it will be added to the same declaration context as the
original struct (the same namespace).

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

Treating `ConstantBuffer` as an alias of `T` would take care the member access
issue; the `.` access refers directly to members of `T`, and global variables
declared using the `ConstantBuffer` syntax would be have the `hlsl_constant`
address space.

On the other hand, we need to make sure `ConstantBuffer` can also be handled as
other resources, i.e. as a record class that contains a resource handle. That
would be useful when creating arrays of `ConstantBuffer<T>` or when
`ConstantBuffer<T>` is used a as function argument. It is not clear how that
would work with the alias declaration.

*At this point the design of the `ConstantBuffer<T>` class is still work in
progress.*


Note that resources and other non-constant buffer constructs should not be
allowed inside the template type `T` used in `ConstantBuffer<T>`. The compiler
should report an error.

### Lowering Constant Buffer Resources to LLVM IR

For each constant buffer the Clang codegen will create a global variable in
default address space. The type of the global will be `target("dx.CBuffer",
...)`. This global variable will be used for the resource handle initialization
and will be eventually removed. The target type `target("dx.CBuffer", ...)` will
include 1 parameter - an explicit HLSL layout type representing the buffer
layout structure.

For example this `cbuffer`:
```
cbuffer MyConstants {
  float2 a;
  int c;
}
```
would be translated a global variable with the following target type:
```
%__cblayout_MyConstants = type <{ <2 x float>, i32 }>
@MyConstants.cb = external constant target("dx.CBuffer", target("dx.Layout", %__cblayout_MyConstants, 12, 0, 8))
```

The explicit HLSL layout types are described
[here](0017-NNNN-explicit-layout-struct.md).

### Lowering Accesses to Individual Constants to LLVM IR

For explicit `HLSLBufferDecl`s declarations (`cbuffer` syntax) Clang codegen
will create global variables for all of its variable declarations. Since the
declaration are already using the `hlsl_constant` address space the global
variables will be declared in this address space as well.

For implicit `HLSLBufferDecl`s declarations (`$Globals` and possibly
`ConstantBuffer<T>` syntax) the declarations already exist at the global scope
in the `hlsl_constant` address space, no changes should be needed here.

Note that these globals are temporary. They will be eventually transformed into
appropriate intrinsics calls and will not exist in the final DXIL or SPIR-V
code.

For example for this HLSL code:

```c++
struct S {
  float f;
};

cbuffer Constants {
  int i;
  S s;
};

cbuffer OtherConstants {
  float4 v;
  int array[10];
};
```

Clang codegen will create these struct definition and global variabless:

```
%__cblayout_Constants = type <{ i32, target("dx.Layout", %S, 4, 0) }>
%S = type <{ float }>
%__cblayout_OtherConstants = type <{ <4 x float>, [10 x i32] }>

@Constants.cb = external constant target("dx.CBuffer", target("dx.Layout", %__cblayout_Constants, 20, 0, 16))
@i = external addrspace(2) global i32, align 4
@s = external addrspace(2) global target("dx.Layout", %S, 4, 0), align 4

@OtherConstants.cb = external constant target("dx.CBuffer", target("dx.Layout", %__cblayout_OtherConstants, 164, 0, 16))
@v = external addrspace(2) global <4 x float>, align 16
@array = external addrspace(2) global [10 x i32], align 4
```

Clang codegen will translate accesses to these global constants to `load`
instruction from a pointer in `addrspace(2)`. These `load` instructions will be
later replaced in an LLVM pass with constant buffer load intrinsic calls on a
buffer resource handle. In order for the pass to generate the correct CBV loads
it is going to need additinal information, such as which constants belong to
which constant buffer. Codegen will generate this information as metadata.

Note that the name of `cbuffer` declaration does not have to be unique. A shader
can have multiple `cbuffer` declarations using the same name. The name of the
layout struct created for the buffer should be derived from the `cbuffer` name.
The compiler must ensure that it is unique by adding a number to the name or
other similar mechanism.

### Format of constant buffer metadata

Clang codegen needs to emit metadata that will link `hlsl_constant` globals  to
individual constant buffers. Metadata node for a single buffer will be a list of
global variables where the first item will be the global variable represending
the constant buffer. It will be followed by 1 or more `hlsl_constant` global
variables that belong to this constant buffer, in the same order as they were
declared in the source code.

A named metadata node `hlsl.cbs` will then store a list all metadata nodes for
individual buffers.

For the HLSL code above the metadata will look like:

```
!hlsl.cbs = !{!1, !2}
!1 = !{ptr @Constants.cb, ptr addrspace(2) @i, ptr addrspace(2) @s}
!2 = !{ptr @OtherConstants.cb, ptr addrspace(2) @v, ptr addrspace(2) @array}
```

### Lowering to buffer load intrinsics

A new pass `HLSLConstantAccess` will translate all `load` instructions in
`hlsl_constant` address space to `llvm.{dx|spv}.resource.load.cbuffer`
intrinsics. It will make use of the metadata generated by Clang codegen that
maps the constants global variables to individual constant buffers. The pass
will also transform related `getelementptr` instructions to use the constant
buffer layout offsets.

After the `HLSLConstantAccess` pass completes the constant globals and the
constant buffer metadata are no longer needed and should be removed.

### Lowering to DXIL

Separate DXIL pass will translate the `llvm.dx.resource.load.cbuffer` intrinsics
to `cbufferLoadLegacy` DXIL ops.

### Handle initialization

Clang codegen will constant buffer handle initialization the same way as it does
with other resource classes like raw buffers or structured buffers.

### Reflectiom consideration

The temporary metadata generated by Clang codegen is not sufficient to generate
shader reflection data. When we are going to design how to produce it, we will
most likely create a additional metadata structures for reflection it which will
not be stripped from the module, and that will contain only the necessary
reflection data.

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
-- Nested `cbuffer` declarations

## Links

[Shader
Constants](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-constants)<br/>
[Packing Rules for Constant
Variables](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-packing-rules)<br/>
[HLSL Constant Buffer Layout
Visualizer](https://maraneshi.github.io/HLSL-ConstantBufferLayoutVisualizer)<br/>
[`packoffset` Attribute](0003-packoffset.md)</br>

## Acknowledgments (Optional)

