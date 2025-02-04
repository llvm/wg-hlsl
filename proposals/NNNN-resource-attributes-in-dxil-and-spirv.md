<!-- {% raw %} -->

# Mapping Resource Attributes to DXIL and SPIR-V

* Proposal: [NNNN](NNNN-resource-attributes-in-dxil-and-spirv.md)
* Author: [Justin Bogner](https://github.com/bogner)
* Status: **Design In Progress**

## Introduction

There are a number of objects in HLSL that map to shader model resources. We
need to represent these in various ways throughout lowering from the HLSL
language to DXIL and SPIR-V program representations suitable for consumption by
GPU drivers.

This document tries to summarize the information that's needed in the various
parts of the compiler, survey DXC's implementation, and ask questions and make
recommendations about how we want to handle all of this in clang.

## Motivation

There are a number of places where we need to represent resource objects
throughout the compiler. From an HLSL language perspective we need to carry
sufficient information in the AST to track these types. At the LLVM IR level we
need target specific types. Finally, the resulting DXIL and SPIR-V have their
own representations.

## Proposed solution

We'll discuss the set of HLSL objects that we need to lower to various types of
resources, how they map to DXIL constructs, how DXC represents these in SPIR-V,
and finally a set of attributes that's sufficient to generate the code we need
in both DXIL and SPIR-V.

### HLSL Objects

The resource objects in HLSL can be divided in a few different ways, but
generally the interesting attributes are the layout and dimensionality and
whether the objects are writeable.

| HLSL Object                        |                                                              |
|------------------------------------|--------------------------------------------------------------|
| Texture1D                          | Read-only 1D texture                                         |
| Texture1DArray                     | Read-only array of 1D textures                               |
| Texture2D                          | Read-only 2D texture                                         |
| Texture2DArray                     | Read-only array of 2D textures                               |
| Texture2DMS                        | Read-only 2D texture with multisampling                      |
| Texture2DMSArray                   | Read-only array of 2D textures with multisampling            |
| Texture3D                          | Read-only 3D texture                                         |
| TextureCUBE                        | Read-only cubemapped texture                                 |
| TextureCUBEArray                   | Read-only array of cubemapped textures                       |
| RWTexture1D                        | Read/Write 1D texture                                        |
| RWTexture1DArray                   | Read/Write array of 1D textures                              |
| RWTexture2D                        | Read/Write 2D texture                                        |
| RWTexture2DArray                   | Read/Write array of 2D textures                              |
| RWTexture2DMS                      | Read/Write 2D texture with multisampling                     |
| RWTexture2DMSArray                 | Read/Write array of 2D textures with multisampling           |
| RWTexture3D                        | Read/Write 3D texture                                        |
| RasterizerOrderedTexture1D         | Read/Write 1D texture with ROV guarantees                    |
| RasterizerOrderedTexture1DArray    | Read/Write array of 1D textures with ROV guarantees          |
| RasterizerOrderedTexture2D         | Read/Write 2D texture with ROV guarantees                    |
| RasterizerOrderedTexture2DArray    | Read/Write array of 2D textures with ROV guarantees          |
| RasterizerOrderedTexture3D         | Read/Write 3D texture with ROV guarantees                    |
| FeedbackTexture2D                  | Texture feedback map                                         |
| FeedbackTexture2DArray             | Array of texture feedback maps                               |
| Buffer                             | Read-only buffer of scalar or vector types                   |
| RWBuffer                           | Read/write buffer of scalar or vector types                  |
| RasterizerOrderedBuffer            | Read/write buffer with ROV guarantees                        |
| ByteAddressBuffer                  | Read-only byte-addressable buffer                            |
| RWByteAddressBuffer                | Read-write byte-addressable buffer                           |
| RasterizerOrderedByteAddressBuffer | Read-write byte-addressable buffer with ROV guarantees       |
| StructuredBuffer                   | Read-only buffer of UDTs                                     |
| RWStructuredBuffer                 | Read-write buffer of UDTs                                    |
| RasterizerOrderedStructuredBuffer  | Read-write buffer of UDTs with ROV guarantees                |
| AppendStructuredBuffer             | Streaming output buffer                                      |
| ConsumeStructuredBuffer            | Streaming Input buffer                                       |
| cbuffer                            | Struct declaration syntax for legacy format constant buffers |
| ConstantBuffer                     | Template syntax for legacy format constant buffers           |
| tbuffer                            | Struct declaration syntax for legacy format texture buffers  |
| TextureBuffer                      | Template syntax for legacy format texture buffers            |
| SamplerState                       | Sampler state                                                |
| SamplerComparisonState             | Sampler comparison state                                     |

A few notes:
- Textures and Buffer/RWBuffer have requirements that their elements fit in a
  scalar or four 4-byte elements, for both historical reasons and because
  they're generally mapped to image formats.
- The layouts cbuffer and tbuffer are tied to DXBC's historical 16-byte row
  layout rules.
- ByteAddress and Structured buffers aren't constrained by image format or
  legacy layout.
- Sampler state is represented by opaque objects that we won't go into too much
  detail about here.

### DXIL

DXIL represents resources in two different and subtly incompatible ways. All
versions of DXIL have [metadata resource records], and since shader model 6.6
we also have the [resource properties] that are bit-packed into the
"annotateHandle" DXIL operation. There appears to be have been intent at some
point to replace the metadata with the annotation model, but my understanding
is that we need to continue to generate both in clang's DXIL implementation to
match DXC.

[Metadata resource records]:
    https://github.com/microsoft/DirectXShaderCompiler/blob/main/docs/DXIL.rst#metadata-resource-records
[resource properties]:
    https://github.com/microsoft/DirectXShaderCompiler/blob/v1.8.2407/include/dxc/DXIL/DxilResourceProperties.h#L23

#### DXIL Metadata

The DXIL metadata records a resource class, a "shape", and a few resource class
dependent properties:

- The Resource class is SRV (Shader resource view), UAV (Unordered Access
  View), CBV (Constant buffer view), or Sampler. This is largely only used for
  determining which register class a resource belongs to, and is mostly
  valuable in differentiating between (writeable) UAVs and (read-only) SRVs.
- The "shape" is more commonly referred to as "resource kind" outside of the
  DXIL docs. This covers all of the texture and buffer types, as well as
  "tbuffer" which maps to the cbuffer layout when the resource class is SRV.
- The resource class dependent properties attempt to cover the variety of
  possibilities per class but have a few issues. See the footnotes below.

|                                    | RC   | "Shape"                | MS Count   | Element Type | Struct Stride | ROV   | CBuf Size | Feedback |
|------------------------------------|------|------------------------|------------|--------------|---------------|-------|-----------|----------|
| Texture1D                          | SRV  | Texture1D              | 0          | enum         | -             | -     | -         | -        |
| Texture1DArray                     | SRV  | Texture1DArray         | 0          | enum         | -             | -     | -         | -        |
| Texture2D                          | SRV  | Texture2D              | 0          | enum         | -             | -     | -         | -        |
| Texture2DArray                     | SRV  | Texture2DArray         | 0          | enum         | -             | -     | -         | -        |
| Texture2DMS                        | SRV  | Texture2DMS            | number[^1] | enum         | -             | -     | -         | -        |
| Texture2DMSArray                   | SRV  | Texture2DMSArray       | number[^1] | enum         | -             | -     | -         | -        |
| Texture3D                          | SRV  | Texture3D              | 0          | enum         | -             | -     | -         | -        |
| TextureCUBE                        | SRV  | TextureCUBE            | 0          | enum         | -             | -     | -         | -        |
| TextureCUBEArray                   | SRV  | TextureCUBEArray       | 0          | enum         | -             | -     | -         | -        |
| RWTexture1D                        | UAV  | Texture1D              | -          | enum         | -             | false | -         | -        |
| RWTexture1DArray                   | UAV  | Texture1DArray         | -          | enum         | -             | false | -         | -        |
| RWTexture2D                        | UAV  | Texture2D              | -          | enum         | -             | false | -         | -        |
| RWTexture2DArray                   | UAV  | Texture2DArray         | -          | enum         | -             | false | -         | -        |
| RWTexture2DMS                      | UAV  | Texture2DMS            | -[^2]      | enum         | -             | false | -         | -        |
| RWTexture2DMSArray                 | UAV  | Texture2DMSArray       | -[^2]      | enum         | -             | false | -         | -        |
| RWTexture3D                        | UAV  | Texture3D              | -          | enum         | -             | false | -         | -        |
| RasterizerOrderedTexture1D         | UAV  | Texture1D              | -          | enum         | -             | true  | -         | -        |
| RasterizerOrderedTexture1DArray    | UAV  | Texture1DArray         | -          | enum         | -             | true  | -         | -        |
| RasterizerOrderedTexture2D         | UAV  | Texture2D              | -          | enum         | -             | true  | -         | -        |
| RasterizerOrderedTexture2DArray    | UAV  | Texture2DArray         | -          | enum         | -             | true  | -         | -        |
| RasterizerOrderedTexture3D         | UAV  | Texture3D              | -          | enum         | -             | true  | -         | -        |
| FeedbackTexture2D                  | UAV  | FeedbackTexture2D      | -          | -            | -             | false | -         | enum     |
| FeedbackTexture2DArray             | UAV  | FeedbackTexture2DArray | -          | -            | -             | false | -         | enum     |
| Buffer                             | SRV  | TypedBuffer            | 0          | enum         | -             | -     | -         | -        |
| RWBuffer                           | UAV  | TypedBuffer            | -          | enum         | -             | false | -         | -        |
| RasterizerOrderedBuffer            | UAV  | TypedBuffer            | -          | enum         | -             | true  | -         | -        |
| ByteAddressBuffer                  | SRV  | RawBuffer              | 0          | -            | -             | -     | -         | -        |
| RWByteAddressBuffer                | UAV  | RawBuffer              | -          | -            | -             | false | -         | -        |
| RasterizerOrderedByteAddressBuffer | UAV  | RawBuffer              | -          | -            | -             | true  | -         | -        |
| StructuredBuffer                   | SRV  | StructuredBuffer       | 0          | -            | number        | -     | -         | -        |
| RWStructuredBuffer                 | UAV  | StructuredBuffer       | -          | -            | number        | false | -         | -        |
| RasterizerOrderedStructuredBuffer  | UAV  | StructuredBuffer       | -          | -            | number        | true  | -         | -        |
| AppendStructuredBuffer             | UAV  | StructuredBuffer       | -          | -            | number        | false | -         | -        |
| ConsumeStructuredBuffer            | UAV  | StructuredBuffer       | -          | -            | number        | false | -         | -        |
| cbuffer                            | CBuf | -                      | -          | -            | -             | -     | number    | -        |
| ConstantBuffer                     | CBuf | -                      | -          | -            | -             | -     | number    | -        |
| tbuffer                            | SRV  | TBuffer                | 0          | u32[^3]      | -             | -     | -         | -        |
| TextureBuffer                      | SRV  | TBuffer                | 0          | u32[^3]      | -             | -     | -         | -        |

[^1]: All SRVs have a sample count, but it's zero when not multisampled.
[^2]: The metadata does not represent sample count for RW multisample textures.
[^3]: For tbuffer, element type seems to always be the enum value 5, for `u32`

#### DXIL Binding Annotation

DXIL binding annotations bit-pack information into two integers, as represented
by the unions in the [DxilResourceProperties] class. This format isn't really
documented, and is probably most easily understood by looking at the
[loadPropsFromResourceBase] method, which populates the class's members.

[DxilResourceProperties]:
    https://github.com/microsoft/DirectXShaderCompiler/blob/v1.8.2407/include/dxc/DXIL/DxilResourceProperties.h#L23
[loadPropsFromResourceBase]:
    https://github.com/microsoft/DirectXShaderCompiler/blob/main/lib/DXIL/DxilResourceProperties.cpp#L139

|                                    | RC   | Kind                   | Align  | UAV   | ROV   | Stride | CBuf Size  | Feedback | Elt Type | Elt Count | MS Count |
|------------------------------------|------|------------------------|--------|-------|-------|--------|------------|----------|----------|-----------|----------|
| Texture1D                          | SRV  | Texture1D              | 0      | false | false | -      | -          | -        | enum     | number    | 0        |
| Texture1DArray                     | SRV  | Texture1DArray         | 0      | false | false | -      | -          | -        | enum     | number    | 0        |
| Texture2D                          | SRV  | Texture2D              | 0      | false | false | -      | -          | -        | enum     | number    | 0        |
| Texture2DArray                     | SRV  | Texture2DArray         | 0      | false | false | -      | -          | -        | enum     | number    | 0        |
| Texture2DMS                        | SRV  | Texture2DMS            | 0      | false | false | -      | -          | -        | enum     | number    | number   |
| Texture2DMSArray                   | SRV  | Texture2DMSArray       | 0      | false | false | -      | -          | -        | enum     | number    | number   |
| Texture3D                          | SRV  | Texture3D              | 0      | false | false | -      | -          | -        | enum     | number    | 0        |
| TextureCUBE                        | SRV  | TextureCUBE            | 0      | false | false | -      | -          | -        | enum     | number    | 0        |
| TextureCUBEArray                   | SRV  | TextureCUBEArray       | 0      | false | false | -      | -          | -        | enum     | number    | 0        |
| RWTexture1D                        | UAV  | Texture1D              | 0      | true  | false | -      | -          | -        | enum     | number    | 0        |
| RWTexture1DArray                   | UAV  | Texture1DArray         | 0      | true  | false | -      | -          | -        | enum     | number    | 0        |
| RWTexture2D                        | UAV  | Texture2D              | 0      | true  | false | -      | -          | -        | enum     | number    | 0        |
| RWTexture2DArray                   | UAV  | Texture2DArray         | 0      | true  | false | -      | -          | -        | enum     | number    | 0        |
| RWTexture2DMS                      | UAV  | Texture2DMS            | 0      | true  | false | -      | -          | -        | enum     | number    | number   |
| RWTexture2DMSArray                 | UAV  | Texture2DMSArray       | 0      | true  | false | -      | -          | -        | enum     | number    | number   |
| RWTexture3D                        | UAV  | Texture3D              | 0      | true  | false | -      | -          | -        | enum     | number    | 0        |
| RasterizerOrderedTexture1D         | UAV  | Texture1D              | 0      | true  | true  | -      | -          | -        | enum     | number    | 0        |
| RasterizerOrderedTexture1DArray    | UAV  | Texture1DArray         | 0      | true  | true  | -      | -          | -        | enum     | number    | 0        |
| RasterizerOrderedTexture2D         | UAV  | Texture2D              | 0      | true  | true  | -      | -          | -        | enum     | number    | 0        |
| RasterizerOrderedTexture2DArray    | UAV  | Texture2DArray         | 0      | true  | true  | -      | -          | -        | enum     | number    | 0        |
| RasterizerOrderedTexture3D         | UAV  | Texture3D              | 0      | true  | true  | -      | -          | -        | enum     | number    | 0        |
| FeedbackTexture2D                  | SRV  | FeedbackTexture2D      | 0      | false | false | -      | -          | enum     | -        | -         | -        |
| FeedbackTexture2DArray             | SRV  | FeedbackTexture2DArray | 0      | false | false | -      | -          | enum     | -        | -         | -        |
| Buffer                             | SRV  | TypedBuffer            | 0      | false | false | -      | -          | -        | enum     | number    | 0        |
| RWBuffer                           | UAV  | TypedBuffer            | 0      | true  | false | -      | -          | -        | enum     | number    | 0        |
| RasterizerOrderedBuffer            | UAV  | Buffer                 | 0      | true  | true  | -      | -          | -        | enum     | number    | 0        |
| ByteAddressBuffer                  | SRV  | RawBuffer              | 0      | false | false | -      | -          | -        | -        | -         | -        |
| RWByteAddressBuffer                | UAV  | RawBuffer              | 0      | true  | false | -      | -          | -        | -        | -         | -        |
| RasterizerOrderedByteAddressBuffer | UAV  | RawBuffer              | 0      | true  | true  | -      | -          | -        | -        | -         | -        |
| StructuredBuffer                   | SRV  | StructuredBuffer       | number | false | false | number | -          | -        | -        | -         | -        |
| RWStructuredBuffer                 | UAV  | StructuredBuffer       | number | true  | false | number | -          | -        | -        | -         | -        |
| RasterizerOrderedStructuredBuffer  | UAV  | StructuredBuffer       | number | true  | true  | number | -          | -        | -        | -         | -        |
| AppendStructuredBuffer             | UAV  | StructuredBuffer       | number | true  | false | number | -          | -        | -        | -         | -        |
| ConsumeStructuredBuffer            | UAV  | StructuredBuffer       | number | true  | false | number | -          | -        | -        | -         | -        |
| cbuffer                            | CBuf | CBuffer                | 0      | false | false | -      | number     | -        | -        | -         | -        |
| ConstantBuffer                     | CBuf | CBuffer                | 0      | false | false | -      | number     | -        | -        | -         | -        |
| tbuffer                            | SRV  | TBuffer                | 0      | false | false | -      | number[^4] | -        | -        | -         | -        |
| TextureBuffer                      | SRV  | TBuffer                | 0      | false | false | -      | number[^4] | -        | -        | -         | -        |

[^4]: LLVM is probably buggy here currently. It differs from DXC and sets
    element type/count instead of cbuf size.
    
#### Target Extension Types

In LLVM IR we'll represent all of the DXIL resource types via [target extension
types], as described in [proposal 0006] and the [DXILResources docs]. As of
this writing these docs don't yet cover the texture types, but they'll follow
from the constraints described here.

[target extension types]:
    https://llvm.org/docs/LangRef.html#target-extension-type
[proposal 0006]:
    https://github.com/llvm/wg-hlsl/blob/main/proposals/0006-resource-representations.md
[DXILResources docs]:
    https://llvm.org/docs/DirectX/DXILResources.html
    
### SPIR-V

DXC's SPIR-V backend treats "Buffer" as a texture and maps [DXC textures]
directly to [OpTypeImage]. In LLVM IR there is a 1-1 correspondence between the
set of SPIR-V target extension types and the resulting OpTypeImage for the
simple cases.

[DXC textures]:
    https://github.com/microsoft/DirectXShaderCompiler/blob/main/docs/SPIR-V.rst#textures
[OpTypeImage]:
    https://registry.khronos.org/SPIR-V/specs/unified1/SPIRV.html#OpTypeImage


|                    | Dim    | Depth       | Arrayed | MS    | Sampled | Image Format |
|--------------------|--------|-------------|---------|-------|---------|--------------|
| Texture1D          | 1D     | Unknown (2) | false   | false | r/o (1) |              |
| Texture1DArray     | 1D     | Unknown (2) | true    | false | r/o (1) |              |
| Texture2D          | 2D     | Unknown (2) | false   | false | r/o (1) |              |
| Texture2DArray     | 2D     | Unknown (2) | true    | false | r/o (1) |              |
| Texture2DMS        | 2D     | Unknown (2) | false   | true  | r/o (1) |              |
| Texture2DMSArray   | 2D     | Unknown (2) | true    | true  | r/o (1) |              |
| Texture3D          | 3D     | Unknown (2) | false   | false | r/o (1) |              |
| TextureCUBE        | Cube   | Unknown (2) | false   | false | r/o (1) |              |
| TextureCUBEArray   | Cube   | Unknown (2) | true    | false | r/o (1) |              |
| RWTexture1D        | 1D     | Unknown (2) | false   | false | r/w (2) |              |
| RWTexture1DArray   | 1D     | Unknown (2) | true    | false | r/w (2) |              |
| RWTexture2D        | 2D     | Unknown (2) | false   | false | r/w (2) |              |
| RWTexture2DArray   | 2D     | Unknown (2) | true    | false | r/w (2) |              |
| RWTexture2DMS      | 2D     | Unknown (2) | false   | true  | r/w (2) |              |
| RWTexture2DMSArray | 2D     | Unknown (2) | true    | true  | r/w (2) |              |
| RWTexture3D        | 3D     | Unknown (2) | false   | false | r/w (2) |              |
| Buffer             | Buffer | Unknown (2) | false   | false | r/o (1) |              |
| RWBuffer           | Buffer | Unknown (2) | false   | false | r/w (2) |              |

Note that dxc generally guesses at the image format for SPIR-V, and there is a
`vk::image_format` attribute in DXC's HLSL implementation that can be used to
choose something in particular. We need to document what we'll be doing here,
considering the many discussions and issues about this over the years in DXC
([#4941], [#4773], [#2498], [#3395], [#4868], ...)

[#4941]: https://github.com/microsoft/DirectXShaderCompiler/issues/4941
[#4773]: https://github.com/microsoft/DirectXShaderCompiler/issues/4773
[#2498]: https://github.com/microsoft/DirectXShaderCompiler/issues/2498
[#3395]: https://github.com/microsoft/DirectXShaderCompiler/issues/3395
[#4868]: https://github.com/microsoft/DirectXShaderCompiler/issues/4868

DXC lowers [Constant/Texture/Structured/Byte Buffers] to [OpTypeStruct] in
SPIR-V with a storage class that depends on the Vulkan version (Uniform or
StorageBuffer) and various layout decorations. DXC tracks the necessary
information to lower these in side structures, and we'll likely need to keep
track of that information in new SPIR-V target extension types in our
implementation.

[Constant/Texture/Structured/Byte Buffers]:
    https://github.com/microsoft/DirectXShaderCompiler/blob/main/docs/SPIR-V.rst#constant-texture-structured-byte-buffers
[OpTypeStruct]:
    https://registry.khronos.org/SPIR-V/specs/unified1/SPIRV.html#OpTypeStruct

|                         | Vulkan Buffer Type | SPIR-V Decoration |
|-------------------------|--------------------|-------------------|
| ByteAddressBuffer       | Storage            | BufferBlock       |
| RWByteAddressBuffer     | Storage            | BufferBlock       |
| StructuredBuffer        | Storage            | BufferBlock       |
| RWStructuredBuffer      | Storage            | BufferBlock       |
| AppendStructuredBuffer  | Storage            | BufferBlock       |
| ConsumeStructuredBuffer | Storage            | BufferBlock       |
| cbuffer                 | Uniform            | Block             |
| ConstantBuffer          | Uniform            | Block             |
| tbuffer                 | Storage            | BufferBlock       |
| TextureBuffer           | Storage            | BufferBlock       |

The "RasterizerOrdered" (or ROV) resources in HLSL don't map directly to
SPIR-V. In DXC, we emulate ROV by treating these the same as their non-ROV
counterparts, wrapping accesses to the resource in critical sections using
[SPV_EXT_fragment_shader_interlock], and then relying on `spirv-opt` to clean
up. We will probably need to extend the SPIR-V target extension types to
represent these, and then have the backend do what it needs to do with that
information.

[SPV_EXT_fragment_shader_interlock]:
    https://github.com/KhronosGroup/SPIRV-Registry/blob/main/extensions/EXT/SPV_EXT_fragment_shader_interlock.asciidoc

|                                    |
|------------------------------------|
| RasterizerOrderedTexture1D         |
| RasterizerOrderedTexture1DArray    |
| RasterizerOrderedTexture2D         |
| RasterizerOrderedTexture2DArray    |
| RasterizerOrderedTexture3D         |
| RasterizerOrderedBuffer            |
| RasterizerOrderedByteAddressBuffer |
| RasterizerOrderedStructuredBuffer  |

Feedback textures aren't implemented in DXC.

|                                    |
|------------------------------------|
| FeedbackTexture2D                  |
| FeedbackTexture2DArray             |

### Attributes

From all of this, we're able to come up with a set of attributes that can
represent all of the texture and buffer types. These should carry sufficient
information to lower to both of the targets:

|                                    | RC   | Type   | ROV | Dim  | MS  | Feedback | Array | Raw | Row |
|------------------------------------|------|--------|-----|------|-----|----------|-------|-----|-----|
| Texture1D                          | SRV  | vec4   | -   | 1D   | -   | -        | -     | -   | -   |
| Texture1DArray                     | SRV  | vec4   | -   | 1D   | -   | -        | yes   | -   | -   |
| Texture2D                          | SRV  | vec4   | -   | 2D   | -   | -        | -     | -   | -   |
| Texture2DArray                     | SRV  | vec4   | -   | 2D   | -   | -        | yes   | -   | -   |
| Texture2DMS                        | SRV  | vec4   | -   | 2D   | yes | -        | -     | -   | -   |
| Texture2DMSArray                   | SRV  | vec4   | -   | 2D   | yes | -        | yes   | -   | -   |
| Texture3D                          | SRV  | vec4   | -   | 3D   | -   | -        | -     | -   | -   |
| TextureCUBE                        | SRV  | vec4   | -   | Cube | -   | -        | -     | -   | -   |
| TextureCUBEArray                   | SRV  | vec4   | -   | Cube | -   | -        | yes   | -   | -   |
| RWTexture1D                        | UAV  | vec4   | -   | 1D   | -   | -        | -     | -   | -   |
| RWTexture1DArray                   | UAV  | vec4   | -   | 1D   | -   | -        | yes   | -   | -   |
| RWTexture2D                        | UAV  | vec4   | -   | 2D   | -   | -        | -     | -   | -   |
| RWTexture2DArray                   | UAV  | vec4   | -   | 2D   | -   | -        | yes   | -   | -   |
| RWTexture2DMS                      | UAV  | vec4   | -   | 2D   | yes | -        | -     | -   | -   |
| RWTexture2DMSArray                 | UAV  | vec4   | -   | 2D   | yes | -        | yes   | -   | -   |
| RWTexture3D                        | UAV  | vec4   | -   | 3D   | -   | -        | -     | -   | -   |
| RasterizerOrderedTexture1D         | UAV  | vec4   | yes | 1D   | -   | -        | -     | -   | -   |
| RasterizerOrderedTexture1DArray    | UAV  | vec4   | yes | 1D   | -   | -        | yes   | -   | -   |
| RasterizerOrderedTexture2D         | UAV  | vec4   | yes | 2D   | -   | -        | -     | -   | -   |
| RasterizerOrderedTexture2DArray    | UAV  | vec4   | yes | 2D   | -   | -        | yes   | -   | -   |
| RasterizerOrderedTexture3D         | UAV  | vec4   | yes | 3D   | -   | -        | -     | -   | -   |
| FeedbackTexture2D                  | SRV  | -      | -   | -    | -   | fbtype   | -     | -   | -   |
| FeedbackTexture2DArray             | SRV  | -      | -   | -    | -   | fbtype   | yes   | -   | -   |
| Buffer                             | SRV  | vec4   | -   | -    | -   | -        | -     | -   | -   |
| RWBuffer                           | UAV  | vec4   | -   | -    | -   | -        | -     | -   | -   |
| RasterizerOrderedBuffer            | UAV  | vec4   | yes | -    | -   | -        | -     | -   | -   |
| ByteAddressBuffer                  | SRV  | -      | -   | -    | -   | -        | -     | yes | -   |
| RWByteAddressBuffer                | UAV  | -      | -   | -    | -   | -        | -     | yes | -   |
| RasterizerOrderedByteAddressBuffer | UAV  | -      | yes | -    | -   | -        | -     | yes | -   |
| StructuredBuffer                   | SRV  | struct | -   | -    | -   | -        | -     | yes | -   |
| RWStructuredBuffer                 | UAV  | struct | -   | -    | -   | -        | -     | yes | -   |
| RasterizerOrderedStructuredBuffer  | UAV  | struct | yes | -    | -   | -        | -     | yes | -   |
| AppendStructuredBuffer             | UAV  | struct | -   | -    | -   | -        | -     | yes | -   |
| ConsumeStructuredBuffer            | UAV  | struct | -   | -    | -   | -        | -     | yes | -   |
| cbuffer                            | CBuf | struct | -   | -    | -   | -        | -     | -   | yes |
| ConstantBuffer                     | CBuf | struct | -   | -    | -   | -        | -     | -   | yes |
| tbuffer                            | SRV  | struct | -   | -    | -   | -        | -     | -   | yes |
| TextureBuffer                      | SRV  | struct | -   | -    | -   | -        | -     | -   | yes |

## Alternatives considered

We could also forgo the large set of specific attributes and boil things down
to mostly resource class and resource kind. This is in some ways simpler, but
has two main downsides:

1. Not quite everything is represented, so we still need attributes for various
   numeric values, and some parameters like feedback type.
2. The resource kind ties us fairly tightly to design decisions in DXIL, so may
   come across as anachronistic as we move to SPIR-V.

For these reasons, I think the broader set of specific attributes is a better
approach.

<!-- {% endraw %} -->
