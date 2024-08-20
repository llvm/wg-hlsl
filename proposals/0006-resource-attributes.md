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

| HLSL Texture Type              | hlsl::resource_class | hlsl::is_rov | hlsl::texture_dimension | hlsl::texture_type |
| ------------------------------- | -------------------- | ------------ | ----------------------- | ------------------ |
| Texture1D                       | SRV                  | -            | 1D                      | -                  |
| RWTexture1D                     | UAV                  | -            | 1D                      | -                  |
| RasterizerOrderedTexture1D      | SRV                  | yes          | 1D                      | -                  |
| Texture1DArray                  | SRV                  | -            | 1DArray                 | -                  |
| RWTexture1DArray                | UAV                  | -            | 1DArray                 | -                  |
| RasterizerOrderedTexture1DArray | SRV                  | yes          | 1DArray                 | -                  |
| Texture2D                       | SRV                  | -            | 2D                      | -                  |
| RWTexture2D                     | UAV                  | -            | 2D                      | -                  |
| RasterizerOrderedTexture2D      | SRV                  | yes          | 2D                      | -                  |
| Texture2DArray                  | SRV                  | -            | 2DArray                 | -                  |
| RWTexture2DArray                | UAV                  | -            | 2DArray                 | -                  |
| RasterizerOrderedTexture2DArray | SRV                  | yes          | 2DArray                 | -                  |
| Texture3D                       | SRV                  | -            | 3D                      | -                  |
| RWTexture3D                     | UAV                  | -            | 3D                      | -                  |
| RasterizerOrderedTexture3D      | SRV                  | yes          | 3D                      | -                  |
| TextureCUBE                     | SRV                  | -            | CUBE                    | -                  |
| TextureCUBEArray                | SRV                  | -            | CUBEArray               | -                  |
| Texture2DMS                     | SRV                  | -            | 2D                      | MS                 |
| Texture2DMSArray                | SRV                  | -            | 2DArray                 | MS                 |
| RWTexture2DMS                   | UAV                  | -            | 2D                      | MS                 |
| RWTexture2DMSArray              | UAV                  | -            | 2DArray                 | MS                 |
| FeedbackTexture2D               | SRV                  | -            | 2D                      | Feedback           |
| FeedbackTexture2DArray          | SRV                  | -            | 2DArray                 | Feedback           |

## Detailed design

## Acknowledgments (Optional)
* Damyan Pepper
<!-- {% endraw %} -->