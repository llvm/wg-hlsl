<!-- {% raw %} -->
* Proposal: [0006](0004-register-types-and-diagnostics.md)
* Author(s): [Joshua Batista](https://github.com/bob80905)
* Sponsor: TBD
* Status: **Under Consideration**
* Impacted Project(s): (LLVM)
* PRs: []
* Issues: [#39](https://github.com/llvm/wg-hlsl/issues/39)

## Introduction
In DXC, binding textures to registers will result in the decl representing
the texture resource having an attribute added to it. This attribute, the
`HLSLResource` attribute, contains the `ResourceKind` enum that contains
an enumeration of all possible resource types. This data is used to inform 
codegen on how to construct the dxil handle that represents the declared
resource.

## Motivation

In LLVM, it is no longer desired to retain this resource kind data within
the `HLSLResource` attribute, and the attribute itself will be removed.
However, after removing this attribute, there will not be sufficient 
information on how to construct the dxil handle. For example, the
resource kind may specify `Texture2DMS`, which would inform the codegen
pass that the given texture has a multi-sample texture type.
With the planned removal of the `HLSLResource` attribute, we need to
substitute the attribute with other attributes that contain enough 
information to construct the dxil handle that needs to be constructed.
For example, an attribute should exist to preserve the information that
the given resource is a texture, and has a multi-sample texture type.

To properly substitute the `HLSLResource` attribute, it should be
confirmed that the proposed substitute attributes are sufficient to
directly reconstruct all defined resource types.

## Proposed Solution
The table below specifies all texture types that exist in HLSL, and
the attributes we would expect to see on the type that defines these
texture variables. We should expect that given any combination of
attributes and values of the attributes, we can directly infer what
the texture type is and how to construct the associated dxil handle.
For example, a `RWTexture2DMSArray` texture would have a definition
in an HLSL header, and the type itself would be constructed with
specific attributes attached to it: `hlsl::resource_class` would be 
`SRV`, `hlsl::is_rov` would not be present, `hlsl::texture_dimension`
would be `2DArray`, and `hlsl::texture_type` would be `MS`.

| HLSL Texture Type               | hlsl::resource_class | hlsl::is_rov | hlsl::texture_dimension | hlsl::is_cube | hlsl::is_ms | hlsl::is_feedback | hlsl::is_array |
| ------------------------------- | -------------------- | ------------ | ----------------------- | ------------- | ----------- | ----------------- | -------------- |
| Texture1D                       | SRV                  | -            | 1                       | -             | -           | -                 | -              |
| RWTexture1D                     | UAV                  | -            | 1                       | -             | -           | -                 | -              |
| RasterizerOrderedTexture1D      | UAV                  | yes          | 1                       | -             | -           | -                 | -              |
| Texture1DArray                  | SRV                  | -            | 1                       | -             | -           | -                 | yes            |
| RWTexture1DArray                | UAV                  | -            | 1                       | -             | -           | -                 | yes            |
| RasterizerOrderedTexture1DArray | UAV                  | yes          | 1                       | -             | -           | -                 | yes            |
| Texture2D                       | SRV                  | -            | 2                       | -             | -           | -                 | -              |
| RWTexture2D                     | UAV                  | -            | 2                       | -             | -           | -                 | -              |
| RasterizerOrderedTexture2D      | UAV                  | yes          | 2                       | -             | -           | -                 | -              |
| Texture2DArray                  | SRV                  | -            | 2                       | -             | -           | -                 | yes            |
| RWTexture2DArray                | UAV                  | -            | 2                       | -             | -           | -                 | yes            |
| RasterizerOrderedTexture2DArray | UAV                  | yes          | 2                       | -             | -           | -                 | yes            |
| Texture3D                       | SRV                  | -            | 3                       | -             | -           | -                 | -              |
| RWTexture3D                     | UAV                  | -            | 3                       | -             | -           | -                 | -              |
| RasterizerOrderedTexture3D      | UAV                  | yes          | 3                       | -             | -           | -                 | -              |
| TextureCUBE                     | SRV                  | -            | 3                       | yes           | -           | -                 | -              |
| TextureCUBEArray                | SRV                  | -            | 3                       | yes           | -           | -                 | yes            |
| Texture2DMS                     | SRV                  | -            | 2                       | -             | yes         | -                 | -              |
| Texture2DMSArray                | SRV                  | -            | 2                       | -             | yes         | -                 | yes            |
| RWTexture2DMS                   | UAV                  | -            | 2                       | -             | yes         | -                 | -              |
| RWTexture2DMSArray              | UAV                  | -            | 2                       | -             | yes         | -                 | yes            |
| FeedbackTexture2D               | SRV                  | -            | 2                       | -             | -           | yes               | -              |
| FeedbackTexture2DArray          | SRV                  | -            | 2                       | -             | -           | yes               | yes            |
| TypedBuffer                     | SRV                  | -            | -                       | -             | -           | -                 | -              |
| RawBuffer                       | SRV                  | -            | -                       | -             | -           | -                 | -              |
| StructuredBuffer                | SRV                  | -            | -                       | -             | -           | -                 | -              |


## Detailed design

## Acknowledgments (Optional)
* Damyan Pepper
<!-- {% endraw %} -->
