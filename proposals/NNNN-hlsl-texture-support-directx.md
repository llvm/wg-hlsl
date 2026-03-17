---
title: "[NNNN] - HLSL Texture Support for DirectX"
params:
  authors:
    - inbelic: Finn Plummer
  status: Under Consideration
  sponsors:
---

## Introduction

This proposal outlines the work required to add core texture/sampler support to
Clang when targeting DirectX/DXIL. It is broken down into two parts:

1. Hello Triangle (Semantics and Signatures): Fills in the remaining
gaps in semantic support, signature metadata generation, and DXContainer output
so that a minimal vertex + pixel shader can run.

2. Textured Cube (Core Texture/Sampler Operations): Defines the Texture/Sampler
types and their methods, defines their lowering to DXIL and updates to allow
for testing in the offload test suite.

## Motivation

Texture resources and samplers are required for graphics programming in HLSL.
Clang does not currently support either when targeting DirectX and there was
not a previous document to concretely outline what features are missing and
need to be implemented.

## Part 1: Hello Triangle

### Goal

Compile a minimal vertex shader + pixel shader pair that renders a triangle,
generating correct DXIL output including signature metadata. Practically, this
means shader entry points with semantic-annotated parameters and return values
will produce valid signature parts in the DXContainer, and the generated code
will correctly load inputs from and store outputs to the pipeline.

### Semantics to Support

The semantics to support are user semantics and all system value semantics
that are confined to to vertex and pixel shader stages. This excludes
semantics that are only applicable with other shader stages (eg.
`SV_GSInstanceID`). In other words, system value semantics to support are all
that are testable without any non-compute/pixel/vertex shader support.

User Semantics:
 - Arbitrary user-defined names (e.g. `POSITION`, `COLOR`, `TEXCOORD`) used
   to pass data between shader stages

System Values:

 - `SV_VertexID`
 - `SV_InstanceID`
 - `SV_Position`
 - `SV_RenderTargetArrayIndex`
 - `SV_ViewPortArrayIndex`
 - `SV_ClipDistance`
 - `SV_CullDistance`
 - `SV_PrimitiveID`
 - `SV_SampleIndex`
 - `SV_IsFrontFace`
 - `SV_Coverage`
 - `SV_InnerCoverage`
 - `SV_Target`
 - `SV_Depth`
 - `SV_DepthLessEqual`
 - `SV_DepthGreaterEqual`
 - `SV_StencilRef`
 - `SV_ViewID`
 - `SV_Barycentrics`
 - `SV_ShadingRate`
 - `SV_StartVertexLocation`
 - `SV_StartInstanceLocation`

**Question:** These are all testable using a RWBuffer in the shader?

See [Semantics Overview](0040-semantics-overview.md#vertex-shader) for
interpretation details.

### Parsing + Sema of Semantic Attr

Semantics are specified as attributes in the HLSL source, annotating entry
point parameters, return values, and struct fields to describe how data maps
to the pipeline's input/output signature registers.

The `HLSLSemanticAttr` mechanism (described in
[Semantics](0031-semantics.md#Parser)) handles:

 - Parsing semantic annotations from HLSL syntax
 - Decomposing a semantic string into a case-insensitive name and optional
   index (e.g. `TEXCOORD3` → name=`TEXCOORD`, index=3)
 - Distinguishing system semantics (`SV_` prefix) from user semantics

And describes the extension to perform stateless validation:

 - Is this system semantic valid for the target shader stage?
 - Is this system semantic compatible with the type it is applied to?
 - Is this system semantic indexable (e.g. `SV_Target0` is valid,
   `SV_Position2` is not)?

The parsing infrastructure for parsing semantic attributes already exists in
Clang as it is shared between SPIR-V/DXIL. The last semantic check does not
appear to be implemented (https://godbolt.org/z/zEYG8b1xE).

The work for this part is to extend `HLSLSemanticAttr` with any missing
system semantic definitions and extend Sema for all listed validations.

**Question:** This does not account for packing qualifers (eg `noperspective`),
should we incorperate that now? If so, we should update
[Semantics](0031-semantics.md) accordingly.

### Code Generation of Signature Loads and Stores

During code generation, entry point parameters and return values annotated with
semantics will be lowered to either a builtin function call or a read/write of
the pipeline's signature registers.

The DirectX backend uses the `llvm.dx.load.input` and `llvm.dx.store.output`
intrinsics. These take a signature element ID (indexing into the signature
metadata) and component indices to identify which signature register row and
 mask to access. `CGHLSLRuntime::handleSemanticStore` and
`CGHLSLRuntime::handleSemanticLoad` will need to be updated to:

 - Recursively traverse struct types to flatten semantic-annotated fields
 - Emit the correct intrinsic call for each scalar/vector component
 - Handle semantic index auto-incrementing for arrays and multi-row types

The codegen follows the recursive approach outlined in
[Semantics](0031-semantics.md#CodeGen): a shared traversal handles semantic
inheritance and index collision detection, then dispatches to target-specific
emission for the load/store intrinsic.

Currently, Clang codegen has the general recursive algorithm implemented, as
such, it handles the semantics that are lowered to a built-in but generates
placeholder calls to `llvm.dx.load.input` and `llvm.dx.store.output` otherwise.

The work here will be to correct how the intrinsic calls are created, assigning
a unique signature element ID per flattened semantic element and emitting the
correct relative row and component indices. The signature element IDs must be
consistent with the metadata schema described below.

Further, the `loadInput` and `storeOutput` DXIL ops must be defined, and the
intrinsics must be scalarized and lowered accordingly.

### Metadata Schema for Signature Information

The input/output signature information must be retained so that it can be
emitted as the appropriate parts in the output DXContainer. This information
will be retained as module metadata that can be used to generate the `ISG1`,
`OSG1` and `PSV` parts.

There is currently no signature metadata representation defined for Clang.

The work here is to define a metadata schema that retains all
information required for the `ISG1`/`OSG1` signature parts and the signature
elements within `PSV`. For each signature element, the metadata must record:

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

The schema description should be added to
[DXIL Signature Metadata](0040-semantics-overview.md#dxil-signature-metadata).

#### Generate DXContainer Signature Parts

The DXContainer format includes dedicated parts for input, output, and patch
constant signatures. The `DXContainerGlobals` pass reads metadata and generates
the global variables that are then written by `DXContainerObjectWriter`. The
binary format been defined in [`BinaryFormat/DXContainer.h`](https://github.com/llvm/llvm-project/blob/main/llvm/include/llvm/BinaryFormat/DXContainer.h).

So, the work is to update the `DXContainerGlobals` pass to:

 - Parse signature module metadata from the LLVM module
 - Populate the defined structs in [`BinaryFormat/DXContainer.h`](https://github.com/llvm/llvm-project/blob/main/llvm/include/llvm/BinaryFormat/DXContainer.h)
   from the metadata

The work to emit the parts is already implemented. This also means that
`obj2yaml` already supports all signature parts produced by DXC, so we have
an existing mechanism to validate the generated parts.

_Note_: The [Container Signature Parts](0040-semantics-overview.md#dxildxbc-container-signature-parts)
should be updated to be consistent with the definitions in `DXContainer.h`.

**Question:** RDAT and STAT parts are not currently supported?

#### Testing Considerations

 - Semantic diagnostics, intrinsic lowering and packing algorithm can be tested
   through regular `lit` testing
 - `obj2yaml` already supports emitting required parts so we can do round-trip
   tests of signature parts and of `DXContainer` generation
 - The offload test suite needs to add tests for the system value semantics to
   ensure they are being generated as expected. The 'Hello Triangle' is already
   added

## Part 2: Textured Cube

### Goal

Compile a vertex + pixel shader pair that renders a textured cube. In practice,
this part is complete when all features described in
[Texture and Sampler Types](0037-texture-and-sampler-types.md) are supported
for the DirectX backend. This means we should support texture sampling, helper
queries, texel loads, texture/sampler types and these can be verified using the
offload test suite.

### Texture/Sampler Types and Methods

Rather than restate much of the same, please refer to
[Texture and Sampler Types](0037-texture-and-sampler-types.md)
for the complete list of texture/sampler types and their methods that are to be
supported. This details the work to be done for implementing each type and
method.

Notably, this does not include:

 - `Store`: UAV texel write
 - `SampleCmpBias`, `SampleCmpLevel`, `SampleCmpGrad`: SM6.7+ comparison sampling
 - `.sample[index][pos]`: the multisampled texture subscript operator
 - `CheckAccessFullyMapped` / status parameter overloads
 - `Feedback` texture/samplers

**Question:** Should these be included? If so, the first step will be to update
the above proposal.

_Note:_  Sampler and texture are modelled as resources and so they will generate
the appropriate `dx.resources` metadata. This means we are not required to
update part generation for the `DXContainer`. Adding the corresponding tests is
required though.

Further, [Texture and Sampler Types](0037-texture-and-sampler-types.md) should
be updated to describe all required diagnostics that should be brought forward
and improved in Clang. For instance, a dedicated error message should be
generated for using methods [invalid with a given shader
stage](https://godbolt.org/z/sn7q1fKbf).

### Shader Flags

The `ShaderFlagsAnalysis` pass will need to be extended to set advanced texture
usage flags when texture operations are present in the module, see
[here](https://github.com/llvm/llvm-project/issues/116137).

### Offload Test Suite

The offload test suite only has sampler support implemented for Vulkan.
DirectX equivalent support will be added. YAML parsing for sampler
descriptors is already handled; the remaining work is wiring up the DirectX
runtime to create sampler and SRV descriptors.

### Testing Considerations

 - Semantic diagnostics and intrinsic lowering can be tested through regular
   `lit` testing
 - `obj2yaml` supports testing of correct generation for resource PSV data
 - As mentioned, the offload test suite will require support for specifying
   Samplers with DirectX. This can be used to validate that the compiler
   selects the correct Sampler for each texture as described
   [here](0037-texture-and-sampler-types.md#detailed-testing-example-samplelevel).

### Out of Scope

The following are excluded from this proposal:

 - `FeedbackTexture2D`, `FeedbackTexture2DArray`: `WriteSamplerFeedback*`
   operations (SM6.5+)
 - `SampleCmpBias`, `SampleCmpLevel`, `SampleCmpGrad`: SM6.7+ comparison sampling
 - `Store`: UAV texel write
 - `.sample[index][pos]`: the multisampled texture subscript operator
 - `CheckAccessFullyMapped` / status parameter overloads
 - PSV `UsedByAtomic64` and RDAT information

## Acknowledgments

Linked for reference, this proposal builds on several existing designs:

- [0031: HLSL Shader Semantics](0031-semantics.md): Semantic parsing and
  codegen design
- [0037: Texture and Sampler Types](0037-texture-and-sampler-types.md):
  Texture type representation, member functions, and codegen
- [0040: HLSL Semantics Overview](0040-semantics-overview.md): Reference
  for semantic behaviour across shader stages
