---
title: "[NNNN] - Vertex + Pixel Shader Workstreams"
params:
  authors:
    - inbelic: Finn Plummer
  status: Under Consideration
  sponsors:
---

## Introduction

This proposal outlines the work required to support vertex and pixel shaders in
Clang. This includes semantic and signature support, texture/sampler types and
their methods, and the extensions to the offload test suite required to
validate them.

The work is organized into six workstreams:

 1. Vertex and Pixel Shader Test Infrastructure
 2. Semantics and Signatures
 3. Core Texture and Sampler Support
 4. Queries, Comparison Sampling, and Gather Methods
 5. Tiled Resources
 6. Feedback Textures

## Motivation

Support for vertex/pixel shaders is required for graphics programming in HLSL.
To support the majority of vertex and pixel shader use-cases it is required
to support all applicable semantics, corresponding input/output signatures and
Texture/Sampler support.

Clang does not currently fully support these when targeting either Vulkan or
DirectX. There was not a previous document to survey and concretely outline
what support is missing and needs to be implemented.

## Semantics to Support

The semantics to support are user semantics and all system value semantics
that are confined to vertex and pixel shader stages. This excludes
semantics that are only applicable with other shader stages (eg.
`SV_CullPrimitive`).

User Semantics:
 - Arbitrary user-defined names (e.g. `POSITION`, `COLOR`, `TEXCOORD`) used
   to pass data between shader stages

System Values:

 - `SV_VertexID`
 - `SV_InstanceID`
 - `SV_Position`
 - `SV_PrimitiveID`
 - `SV_IsFrontFace`
 - `SV_Target`
 - `SV_ClipDistance`/`SV_CullDistance`
 - `SV_Barycentrics`
 - `SV_StartVertexLocation`/`SV_StartInstanceLocation`
 - `SV_RenderTargetArrayIndex`/`SV_ViewPortArrayIndex`
 - `SV_Depth`/`SV_DepthLessEqual`/`SV_DepthGreaterEqual`/`SV_StencilRef`
 - `SV_SampleIndex`
 - `SV_Coverage`/`SV_InnerCoverage`
 - `SV_ViewID`
 - `SV_ShadingRate`

All can be tested at the compiler IR level; end-to-end testing of many
semantics will require additional runtime features (depth/stencil, MSAA, etc.),
this is addressed in Workstream 1.

See [Semantics Overview](0040-semantics-overview.md#vertex-shader) for
interpretation details.

## Workstream 1: Vertex and Pixel Shader Test Infrastructure

### Goal

The offload test suite has infrastructure to write individual tests for
semantics and texture/sampler methods. As noted below, there are a number of
runtime features that are not supported in the offload test suite, which should
all be added for completion of this workstream.

### Missing Features

The offload test suite requires the following runtime features:

 - Sampler and SRV descriptor creation, to bind textures and samplers to
   shader registers. Implemented for Vulkan but not DirectX.
 - Comparison sampler descriptor creation, to create samplers with a
   `ComparisonFunc` for `SampleCmp` and `GatherCmp` methods.
 - `Texture*Array` type support, to test array texture types for both
   backends.
 - Depth/stencil buffer support, to test `SV_Depth`,
   `SV_DepthLessEqual`, `SV_DepthGreaterEqual`, and `SV_StencilRef`.
 - MSAA render target support, to test `SV_SampleIndex` and
   `SV_Coverage`.
 - Conservative rasterization, to test `SV_InnerCoverage`.
 - Multiple viewport support, to test `SV_ViewPortArrayIndex`.
 - Multi-view rendering, to test `SV_ViewID`.
 - Variable rate shading, to test `SV_ShadingRate`.

### Required Tests

As the infrastructure to write tests becomes available, it is required to have
an end-to-end offload test for each system value semantic and for each
texture/sampler method. This workstream contains the work to write these
individual test cases.

## Workstream 2: Semantics and Signatures

### Goal

Compile a minimal vertex shader + pixel shader pair that renders a triangle,
generating correct DXIL output including signature metadata. Practically, this
means shader entry points with semantic-annotated parameters and return values
will produce valid signature parts in the DXContainer, and the generated code
will correctly load inputs from and store outputs to the pipeline.

### Parsing + Sema of Semantic Attr

Semantics are specified as attributes in the HLSL source, annotating entry
point parameters, return values, and struct fields to describe how data maps
to the pipeline's input/output signature registers.

The [semantics proposal](0031-semantics.md) describes the approach for
targeting both SPIR-V/DirectX targets.

The `HLSLSemanticAttr` mechanism handles:

 - Parsing semantic annotations from HLSL syntax
 - Decomposing a semantic string into a case-insensitive name and optional
   index (e.g. `TEXCOORD3` → name=`TEXCOORD`, index=3)
 - Distinguishing system semantics (`SV_` prefix) from user semantics

And describes the stateless validation:

 - Is this system semantic valid for the target shader stage?
 - Is this system semantic compatible with the type it is applied to?
 - Is this system semantic indexable (e.g. `SV_Target0` is valid,
   `SV_Position2` is not)?

With exception to the last [semantic check](https://godbolt.org/z/zEYG8b1xE),
parsing/sema is already implemented in Clang.

However, the proposal does not account for
[interpolation qualifiers](0040-semantics-overview.md#interpolation-modes)
(`noperspective`, `nointerpolation`, etc.).

#### Work required

 - Extend `HLSLSemanticAttr` with all missing system semantic definitions
 - Implement the system semantic indexable validation
 - Update the [semantics proposal](0031-semantics.md) to account for qualifiers
 - Implement qualifier parsing/sema support on `HLSLSemanticAttr`

### Code Generation of Signature Loads and Stores

During code generation, entry point parameters and return values annotated with
semantics will be lowered to either a builtin function call or a read/write of
the pipeline's signature registers.

Codegen follows a recursive approach outlined in
[Semantics](0031-semantics.md#CodeGen): a shared traversal handles semantic
inheritance and index collision detection, then dispatches to target-specific
emission for the load/store intrinsic.

Clang has this general algorithm implemented and the dispatch to SPIR-V
emission supports existing semantics. When targeting DirectX it emits
placeholder calls to `llvm.dx.load.input` and `llvm.dx.store.output`.
assigning a unique signature element ID per flattened semantic element and
emitting the correct relative row and component indices. The signature element
IDs must be consistent with the metadata schema described below.

#### Work Required

 - Correct how intrinsic calls are called for DirectX
 - Define the `loadInput` and `storeOutput` DXIL ops
 - The `input/output` intrinsics must be scalarized and lowered accordingly.

### Metadata Schema for Signature Information

The input/output signature information must be retained so that it can be
emitted as the appropriate parts in the output DXContainer. This information
will be retained as module metadata that can be used to generate the `ISG1`,
`OSG1` and `PSV` parts.

There is currently no intermediate signature metadata representation defined
for Clang. The schema must retain all information required for the
`ISG1`/`OSG1` signature parts and the signature elements within `PSV`. For each
signature element, the metadata must record:

 - Semantic name: the user or system semantic string
 - Semantic index: differentiates elements sharing the same name
 - System value: `NONE` for user semantics, an enum value for system
   semantics (e.g. `SV_Position` → `POSITION`)
 - Register: which 4-component register row the element occupies
 - Mask: which components (xyzw) within the register are used
 - Format: the data type (e.g. `float`, `int`, `uint`)
 - Min precision: minimum precision qualifier, if applicable
 - Stream: geometry shader output stream index (0 for VS/PS)
 - Input/Output kind: whether the element belongs to the input,
   output, or patch constant signature

Register assignment will implement the complete
[DXIL signature packing rules](https://github.com/Microsoft/DirectXShaderCompiler/blob/main/docs/DXIL.rst#signature-packing)
(prefix-stable, first-fit) respecting constraints on dynamic indexing, type
mixing, and interpolation modes, see
[Packing Constraints](0040-semantics-overview.md#signature-packing-constraints) for
further details.

#### Work Required

 - Define an intermediate module metadata schema containing the above
   information and describe it in a proposal
 - Update `CGHLSLCodeGen` to generate the module metadata

### Generate DXContainer Signature Parts

The DXContainer format includes dedicated parts for input, output, and patch
constant signatures. The `DXContainerGlobals` pass reads metadata and generates
the global variables that are then written by `DXContainerObjectWriter`. The
binary format been defined in `BinaryFormat/DXContainer.h`.

The work to emit the parts is already implemented. This also means that
`obj2yaml` already supports all signature parts produced by DXC, so we have
an existing mechanism to validate the generated parts.

#### Work Required

 - Parse signature module metadata from the LLVM module
 - Populate the defined structs in `BinaryFormat/DXContainer.h` from the
   metadata
 - Ensure [Container Signature Parts](0040-semantics-overview.md#dxildxbc-container-signature-parts)
   is consistent with the definitions in `DXContainer.h`.

## Workstream 3: Core Texture and Sampler Support

### Goal

Support all texture and sampler type declarations, complete the DXIL backend
lowering for the basic sampling methods, and implement texture load/store
access + operators.

### Texture/Sampler Types and Methods

Rather than restate much of the same, please refer to
[Texture and Sampler Types](0037-texture-and-sampler-types.md)
for the complete list of texture/sampler types and their methods that are to be
supported. The proposal details the work to be done for implementing each type
and method.

Clang already has the frontend implemented for the `Texture2D` type, `Sampler`
type and the listed `Sample` methods. These are implemented for SPIR-V but have
similar placeholder `dx` intrinsics otherwise.

_Note:_ Sampler and texture are modelled as resources and so they should
generate the appropriate `dx.resources` metadata. This means we are not
required to update part generation for the `DXContainer`. Adding the
corresponding tests is required though.

The proposal does not enumerate all the diagnostics that should be provided in
Clang. For instance, a dedicated error message should be generated for using
methods [invalid with a given shader stage](https://godbolt.org/z/sn7q1fKbf).

### Methods to Support

 - `Load`/`Store`/`operator[]`
 - `.mips[level][pos]`
 - `.sample[index][pos]`
 - `Sample`/`SampleBias`/`SampleGrad`/`SampleLevel`

`Store` and `.sample[index][pos]` are not currently described in
[Texture and Sampler Types](0037-texture-and-sampler-types.md).

#### Work Required:

 - Update proposal to describe semantic validations
 - Update proposal to describe support for the `Store` method and `.sample`
   operator
 - Implement all Texture and Sampler types
 - Add support for listed methods/operators

### Shader Flags

The `ShaderFlagsAnalysis` pass will need to be extended to set advanced texture
usage flags when texture operations are present in the module, see
[here](https://github.com/llvm/llvm-project/issues/116137).

## Workstreams 4-6: Method Extensions

### Goal

The remaining workstreams follow the same goal to implement a sub-set of the
remaining methods. And have similar work required. When all these workstreams
are complete, then all texture/sampler methods are implemented.

#### Work Required

 - Update the proposal to include support for missing methods
 - Add missing functionality to the offload test suite
 - Implement methods as described

### Workstream 4: Query, Comparison Sampling and Gather Methods

 - `GetDimensions`
 - `CalculateLevelOfDetail`
 - `CalculateLevelOfDetailUnclamped`

 - `SampleCmp`
 - `SampleCmpLevelZero`
 - `SampleCmpBias`
 - `SampleCmpLevel`
 - `SampleCmpGrad`

 - `GatherRed`, `GatherGreen`, `GatherBlue`, `GatherAlpha`
 - `GatherCmpRed`, `GatherCmpGreen`, `GatherCmpBlue`, `GatherCmpAlpha`

`SampleCmpBias`, `SampleCmpLevel`, `SampleCmpGrad` are not currently
described in [Texture and Sampler Types](0037-texture-and-sampler-types.md).

### Workstream 5: Tiled Resource Methods

Add status parameter overloads to `Load`, `Store`, `Sample*`, and `Gather*`
methods that return a status value for `CheckAccessFullyMapped`.

`CheckAccessFullyMapped` is not currently described in
[Texture and Sampler Types](0037-texture-and-sampler-types.md).

Testing tiled resources end-to-end requires creating reserved (sparse) textures
with mapped/unmapped tiles in the offload test suite.

## Workstream 6: Feedback Textures

### Types and Methods

 - `FeedbackTexture2D`, `FeedbackTexture2DArray`
 - `WriteSamplerFeedback`
 - `WriteSamplerFeedbackBias`
 - `WriteSamplerFeedbackLevel`
 - `WriteSamplerFeedbackGrad`

These record which mip levels were accessed by a sampling operation, used for
texture streaming systems.

Testing requires creating feedback texture resources in the offload test suite.

### Out of Scope

The following are excluded from this proposal:

 - PSV `UsedByAtomic64` and RDAT/STAT information

## Acknowledgments

Linked for reference, this proposal builds on several existing designs:

- [0031: HLSL Shader Semantics](0031-semantics.md): Semantic parsing and
  codegen design
- [0037: Texture and Sampler Types](0037-texture-and-sampler-types.md):
  Texture type representation, member functions, and codegen
- [0040: HLSL Semantics Overview](0040-semantics-overview.md): Reference
  for semantic behaviour across shader stages
