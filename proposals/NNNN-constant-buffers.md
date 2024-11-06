
# Constant buffers

* Proposal: [NNNN](NNNN-constant-buffers.md)
* Author(s): [Helena Kotas](https://github.com/hekota)
* Status: **Design In Progress**

## Introduction

Shader inputs usually include a number of constants which are stored in one or more buffer resources in memory with specific packing rules. These resources can be organized into two types of buffers: constant buffers and texture buffers.

From the compiler point of view constant buffers and texture buffers are very similar. The major difference is that constant buffers load from a constant buffer view (CBV) and bind to register `b` while texture buffers load from a typed buffer (SRV) and bind to the `t` register.

Declaring a constant buffer or a texture buffer looks very much like a structure declaration in C, with the addition of the register and packoffset keywords for manually assigning registers or packing data.

```
[cbuffer|tbuffer] ConstBufferName [register(b#)|register(t#)]  {
  VariableDeclaration [ : packoffset(<offset>) ];
  ...
}
```

Constant buffer variables can be accessed anywhere from a shader using the variable name without referencing the constant buffer name. 

Another way of declaring buffers with constants is via `ConstantBuffer` or `TextureBuffer` resource classes. This document currently focuses on the first style of declaration and primarily on `cbuffer`.


## Motivation

We need to support constant buffers in Clang as they are a fundamental part of the HLSL language. 

## Proposed solution

### Parsing cbuffer declaration

In Clang frontend the `cbuffer` declarations will be parsed into a new AST Node called `HLSLConstantBufferDecl`. This class will be based on from `NameDecl` and `DeclContext`.

Variable declarations inside the `cbuffer` context will be children of this new AST node. If a variable declaration specifies a `packoffset`, this information will be parsed into an attribute `HLSLPackOffsetAttr` and applied to the variable declaration. See [packoffset attribute](0003-packoffset.md).

In order to make the variables declared in constant buffer exposed into global scope we can take advantage of `DeclContext::isTransparentContext` and make sure it is true for `HLSLConstantBufferDecl`.

Because the syntax similarities the`tbuffer` declaration will also be using `HLSLConstantBufferDecl` AST node. The method `isCBuffer()` can be used to determine which kind of constant buffer the declaration represents.

*Note: This is already implemented in Clang as `HLSLBufferDecl`. Since constant buffers are not the only buffers in HLSL we should rename it to `HLSLConstantBufferDecl`.*

*Q: Does resource handle with typed attributes come into play here at all?*

### Lowering cbuffer to LLVM

Constant buffers will be lowered to global variables with LLVM target type `target("dx.CBuffer", ..)`. In addition to the type name (`"dx.CBuffer"`) LLVM target types can also include a list of types and a list of integer constants. Any information needed for lowering to DXIL or SPIRV needs to be encoded using these parameters. To encode the shape of the `cbuffer` we can set the type parameter of the LLVM target type to be a struct with all of the `cbuffer` variable declarations.

For example:

```c++
cbuffer MyConstants {
  float2 a;
  float b[2];
  int c;
}
```

Would be lowered to LLVM target type:

```
@MyConstants.cb = global target("dx.CBuffer", %struct.MyConstants = type { <2 x float>, [2 x float], int })
```

### Lowering cbuffer variable access

The layout of constant buffers will be calculated during codegen in `CGHLSLRuntime`, which will also take into account `packoffset` attributes.

Access to `cbuffer` variables will be lowered to LLVM IR the same way as other resource types lower read-only access via subscript operator, except it will use the calculated layout offset. The constant value access would be translated into a memory access in a specific "resource address space" using the `cbuffer` global variable and offset.

### DXIL Lowering

Later, during lowering to DXIL, an LLVM pass would translate these specific "resource address space" memory accesses into `cbufferLoadLegacy` DXIL ops. This pass would take into account specific constant buffer layout rules (loading data one row at a time and extracing specific elements).

### Handle initialization

Constant buffers will be initialized the same way as other resources using the `createHandleFromBinding` intrinsics. Module initialization will need to be updated to initialize all the constant buffers declared in a shader in addition to initialization of resource declared in global variables.

## Detailed design

*TBD*

## Alternatives considered (Optional)

Should we handle the constant buffer layout and `packoffset` later? Should we encode it int into the CBuffer LLVM target type?

## Links

[Shader Constants](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-constants)<br/>
[Packing Rules for Constant Variables](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-packing-rules)<br/>
[HLSL Constant Buffer Layout Visualizer](https://maraneshi.github.io/HLSL-ConstantBufferLayoutVisualizer)<br/>
[`packoffset` Attribute](0003-packoffset.md)

## Acknowledgments (Optional)

