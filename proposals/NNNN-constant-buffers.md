
# Constant buffers

* Proposal: [NNNN](NNNN-constant-buffers.md)
* Author(s): [Helena Kotas](https://github.com/hekota)
* Status: **Design In Progress**

## Introduction

Shader inputs usually include a number of constants which are stored in one or
more buffer resources in memory with specific packing rules. These resources can
be organized into two types of buffers: constant buffers and texture buffers.
This document describes design decisions related to constant buffers.

Constant buffer loads from a constant buffer view (CBV) and binds to register
`b`. It can be declared using the `cbuffer` keyword and it looks very much like
a structure declaration in C, with the addition of the register and packoffset
keywords for manually assigning registers or packing data. For example:

```c++
cbuffer MyConstant : register(b1)  {
  float4 F;
}
```

Constant buffer variables declared within the `cbuffer` scope can be accessed
anywhere from a shader by directly using the variable name (`F`) without
referencing the name of the constant buffer. 

Another way of declaring constant buffers is  with via `ConstantBuffer` class:

```c++
struct MyConstants {
  float4 F;
};

ConstantBuffer<MyConstants> CB;
```
 
In this case the buffer variables are referenced as if they were members of the
`ConstantBuffer` class: `CB.F`.

## Motivation

We need to support constant buffers in Clang as they are a fundamental part of
the HLSL language. 

## Proposed Solution

### Parsing `cbuffer` Declaration

In Clang frontend the `cbuffer` declaration will be parsed into a new AST Node
called `HLSLConstantBufferDecl`. This class will be based on from `NameDecl` and
`DeclContext`.

Variable declarations inside the `cbuffer` context will be children of this new
AST node. If a variable declaration specifies a `packoffset`, this information
will be parsed into an attribute `HLSLPackOffsetAttr` and applied to the
variable declaration. See [packoffset attribute](0003-packoffset.md).

In order to make the variables declared in constant buffer exposed into global
scope we can take advantage of `DeclContext::isTransparentContext` method and
overload it to return true for `HLSLConstantBufferDecl`. This is the same way
variables declared in `export` declaration context are exposed at the global
scope.

*Note: This is already implemented in Clang as `HLSLBufferDecl`. Since constant
buffers are not the only buffers in HLSL we should rename it to
`HLSLConstantBufferDecl`.*

### Parsing `ConstantBuffer` declaration

`ConstantBuffer` definition will be added to the `HLSLExternalSemaSource` the
same way as other resource classes. It will have a resource handle with
`CBuffer` resource class and the contained type would be the template type
argument. It will be handled as other resources classes, for example it can be
passed into a function. 

At the same time Clang needs to recognize this class represents a constant
buffer and the contained type fields are accessed using the `.` operator on
`ConstantBuffer` instance. In other words treating `ConstantBuffer<MyConstants>
CB;` as if it was declared as `cbuffer __CB { MyConstants CB; }`. The exact way
how to do this is TBD.

### Lowering Constant Buffers to LLVM IR

During CodeGen constant buffers will be lowered to global variables with LLVM
target type `target("dx.CBuffer", ..)` which will include type information about
constants, the buffer size and its memory layout.

Note: LLVM target types can optionally include a list of one or more types and a
list of one or more integer constants. We can use these lists to encode any
information needed for lowering from LLVM IR to DXIL and SPIRV.

To encode the shape of the constant buffer the LLVM target type will include a
structure type that represents the constant buffer variable declarations.

The size of the constant buffer will be included as the first item in the list
of integer constants. The rest of the list will be used to encode the constant
buffer layout. The layout will always be included whether the constant buffer
uses any `packoffset` attributes or not. The exact way how the layout will be
encoded is TBD and will be covered in a separate design document.

For simplicity, let's assume the layout will be encoded as a list of offsets of
all cbuffer declarations. In that case this example:

```c++
cbuffer MyConstants {
  float2 a;
  float b[2];
  int c;
}
```

Would be lowered to LLVM target type:

```
@MyConstants.cb = global target("dx.CBuffer", { <2 x float>, [2 x float], i32}, 40, 0, 16, 32, 36)
```

This layout encoding can obviously get very long and unwieldy for more
complicated cbuffers, and especially since target type parameters are all
included in the name mangling for function overloads. We need to investigate how
to make it smaller, or at least more manageable.

One possibility is compressing the list of offsets into a smaller number of
integers - taking advantage of the fact that outside of `packoffset` use the
difference between two adjancent offsets is never more than 16. The compression
could also include repetition construct that would help with encoding of array
offset. But, as with any compressions, there's always the chance of degenerate
cases that will end up with the compressed shape being the same size or larger
than the original.

> Note: The most tricky part of the layout encoding are probably arrays of
> structures because the structure-specific layout gets repeated many times and
> might not be easy to compress. One idea how to solve this could be translating
> structures embedded in `cbuffer` into separate target types with their own
> encoded layout and including them in the `cbuffer` target type. It is not
> clear though if this is possible (probably yes) or if it would actually make
> things easier or not.

Another way could be introducing a typedef concept into the LLVM IR textual
representation so that the full LLVM target type with long layout representation
could occur just once.

### Lowering ConstantBuffer to LLVM IR

The result of codegen for `cbuffer` and `ConstantBuffer` code should be
identical.

### Lowering Constant Buffer Variable Access

Accesses to `cbuffer` variables will be lowered to LLVM IR as memory accesses in
specific "resource address space" using the standard C++ structure layout rules.

### DXIL Lowering

LLVM pass `DXILResourceAccess` will translate these specific "resource address
space" memory accesses into cbuffer DXIL ops adjusting the offsets using the
cbuffer layout information encoded in `target("dx.CBuffer", ..)`. That means
translating standand C++ structure layout offsets to cbuffer layout offsets and
replacing the memory accesses with `llvm.dx.cbufferBufferLoad`,
`llvm.dx.cbufferBufferStore`, and `extractelement ` instructions. The load and
store instructions will be later lowered to `cbufferLoadLegacy` and
`cbufferStoreLegacy` DXIL ops.

### Handle initialization

Constant buffers will be initialized the same way as other resources using the
`createHandleFromBinding` intrinsics. Module initialization code need to be
updated to include all constant buffers declared in a shader.

## Detailed design

*TBD*

## Alternatives considered

- Generate access to `cbuffer` varibles as memory accesses with the offset based
  on cbuffer layout and treat cbuffers as one big type-less memory blob in LLVM
  IR.
  - There is a concern that losing the type information could lead to
    unnecessary copying of values.

- Using type annotations to store cbuffer layout information. Subtypes would
  have its own layout annotations.
  - This is something we can fall back to if encoding the cbuffer layout on LLVM
    target type turns out to be too unwieldy, especially when it comes to
    encoding the layout of an array of structures.

## Open issues
- How to encode the cbuffer layout into LLVM target type
- How to implement `ConstantBuffer` member access
- Handling of `$Globals` constant buffer
- Nested `cbuffer` declarations

## Links

[Shader
Constants](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-constants)<br/>
[Packing Rules for Constant
Variables](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-packing-rules)<br/>
[HLSL Constant Buffer Layout
Visualizer](https://maraneshi.github.io/HLSL-ConstantBufferLayoutVisualizer)<br/>
[`packoffset` Attribute](0003-packoffset.md)</br>

## Acknowledgments (Optional)

