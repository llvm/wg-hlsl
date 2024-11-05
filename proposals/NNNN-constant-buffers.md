
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

Constant buffers will be lowered to LLVM target type `target(dx.CBuffer, ..)`. The LLVM target types can include a list of types and a list of integer constants. Any information needed for lowering to DXIL or SPIRV needs to be encoded using these parameters.

To encode the shape of the `cbuffer` we can use the type  parameter of the LLVM target type to be a struct with all of the `cbuffer` variable declarations.

To encode the `packoffset` information we can use the list of integer constant on the target type. If there is no `packoffset` specified, the list would be empty. If the `cbuffer` variables have a `packoffset`, then the target type would contain a list of constant integers where `n`-th constant would either be a non-negative number specifying the packoffset of the `n`-th variable. 

**Note: `packoffset` offset must either be specified of all `cbuffer` variable declarations or on none.*

For example:

```c++
cbuffer MyConstants {
  float2 a : packoffset(c0.x);
  int2 b : packoffset(c1.z);
}
```

Would be lowered to LLVM target type:

```
target("dx.CBuffer", %struct.MyConstants = type { <2 x float>, <2 x i32> }, 0, 6)
```

### Lowering cbuffer variable access

Access to `cbuffer` variables would be lowered to LLVM in the same way and other resource types handle read-only subscript operator. The constant value access would be translated into a memory access in a specific "resource address space". This would be a simple "resource pointer arithmetic".

Later, during lowering to DXIL, an LLVM pass would translate these specific "resource address space" memory accesses into `cbufferLoadLegacy` DXIL ops. This pass would take into account specific constant buffer layout rules and `packoffset` data, which are specific to DirectX.

### Handle initialization

Constant buffers will be initialized the same way as other resources using the `createHandleFromBinding` intrinsics. Module initialization will need to be updated to initialize all the constant buffers declared in a shader in addition to initialization of resource declared in global variables.

## Detailed design

*TBD*

## Alternatives considered (Optional)

Should we handle the constant buffer layout and `packoffset` info earlier?

## Links

[Shader Constants](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-constants)<br/>
[HLSL Constant Buffer Layout Visualizer](https://maraneshi.github.io/HLSL-ConstantBufferLayoutVisualizer)<br/>
[packoffset attribute](0003-packoffset.md)

## Acknowledgments (Optional)

Take a moment to acknowledge the contributions of people other than the author
and sponsor.

<!-- {% endraw %} -->
