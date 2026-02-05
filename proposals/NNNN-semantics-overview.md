---
title: "NNNN - HLSL Semantics Overview"
params:
  authors:
    - tex3d: Tex Riddell
  status: Design In Progress
--- 

Related to the [0031-semantics.md](0031-semantics.md) proposal, but meant to be
a more comprehensive overview of the current state of semantics and shader
parameters in HLSL, as implemented by DXC.

## Contents

- [Contents](#contents)
- [Introduction](#introduction)
- [Motivation](#motivation)
- [HLSL Syntax](#hlsl-syntax)
- [Ignored semantics](#ignored-semantics)
- [Active semantics](#active-semantics)
  - [Legacy Semantics](#legacy-semantics)
- [Signature Element Translation](#signature-element-translation)
  - [Basic Parameters and Return Types](#basic-parameters-and-return-types)
  - [Basic Arrays](#basic-arrays)
  - [Matrix Types](#matrix-types)
  - [Matrix Arrays](#matrix-arrays)
  - [Structure Types](#structure-types)
  - [Struct Arrays](#struct-arrays)
  - [Special Parameters and Objects](#special-parameters-and-objects)
- [Semantic Assignment](#semantic-assignment)
  - [Semantics on struct fields](#semantics-on-struct-fields)
    - [Semantic override](#semantic-override)
- [Gathering Signature Elements](#gathering-signature-elements)
  - [Signature Points](#signature-points)
    - [Vertex Shader](#vertex-shader)
    - [Pixel Shader](#pixel-shader)
    - [Geometry Shader](#geometry-shader)
    - [Hull Shader](#hull-shader)
    - [Domain Shader](#domain-shader)
    - [Compute, Mesh, and Amplification Shaders](#compute-mesh-and-amplification-shaders)
    - [Node Shaders](#node-shaders)
    - [Raytracing Shaders](#raytracing-shaders)
  - [System Value Constraints](#system-value-constraints)
  - [System Value Details](#system-value-details)
    - [VertexID](#vertexid)
    - [InstanceID](#instanceid)
    - [Position](#position)
    - [RenderTargetArrayIndex and ViewPortArrayIndex](#rendertargetarrayindex-and-viewportarrayindex)
    - [ClipDistance and CullDistance](#clipdistance-and-culldistance)
    - [OutputControlPointID](#outputcontrolpointid)
    - [DomainLocation](#domainlocation)
    - [PrimitiveID](#primitiveid)
    - [GSInstanceID](#gsinstanceid)
    - [SampleIndex](#sampleindex)
    - [IsFrontFace](#isfrontface)
    - [Coverage](#coverage)
    - [InnerCoverage](#innercoverage)
    - [Target](#target)
    - [Depth](#depth)
    - [DepthLessEqual and DepthGreaterEqual](#depthlessequal-and-depthgreaterequal)
    - [StencilRef](#stencilref)
    - [DispatchThreadID](#dispatchthreadid)
    - [GroupID](#groupid)
    - [GroupIndex](#groupindex)
    - [GroupThreadID](#groupthreadid)
    - [TessFactor](#tessfactor)
    - [InsideTessFactor](#insidetessfactor)
    - [ViewID](#viewid)
    - [Barycentrics](#barycentrics)
    - [ShadingRate](#shadingrate)
    - [CullPrimitive](#cullprimitive)
    - [StartVertexLocation and StartInstanceLocation](#startvertexlocation-and-startinstancelocation)
- [DirectX and DXIL](#directx-and-dxil)
  - [Shader Signatures and Attribute Space](#shader-signatures-and-attribute-space)
  - [Signature Packing Constraints](#signature-packing-constraints)
    - [Dynamic Indexing](#dynamic-indexing)
    - [Mixing non-32-bit types](#mixing-non-32-bit-types)
    - [Interpolation Modes](#interpolation-modes)
  - [DXIL Signature Metadata](#dxil-signature-metadata)
  - [DXIL/DXBC Container Signature Parts](#dxildxbc-container-signature-parts)
- [Vulkan and SPIR-V](#vulkan-and-spir-v)
- [Examples](#examples)
  - [Examples - Basic Parameters and Return Types](#examples---basic-parameters-and-return-types)
  - [Examples - Basic Arrays](#examples---basic-arrays)
  - [Examples - Matrix Types](#examples---matrix-types)
  - [Examples - Matrix Arrays](#examples---matrix-arrays)
  - [Examples - Structure Types](#examples---structure-types)
  - [Examples - Struct Arrays](#examples---struct-arrays)
  - [Examples - Special Parameters and Objects](#examples---special-parameters-and-objects)
  - [Examples - Semantic override](#examples---semantic-override)
  - [Examples - Multiple Semantics on Same Declaration](#examples---multiple-semantics-on-same-declaration)
  - [Examples - Passthrough HS](#examples---passthrough-hs)
  - [Examples - Node Shader](#examples---node-shader)
- [Quirks and Compatibility Notes](#quirks-and-compatibility-notes)
  - [Elements from nested fields](#elements-from-nested-fields)

## Introduction

The purpose of this document is to describe how HLSL semantics are defined and
implemented today by the DirectX Shader Compiler (DXC).
It will also reference FXC (Effects Compiler) behavior for background/historical
precedent, and to clarify intentions.
DXC was initially meant to match FXC, but has some bugs, deprecations, and
has newer features not supported by FXC.

The perspective of this document is mostly DirectX/DXIL focused,
since that's the primary target for HLSL historically,
and DirectX defined the constraints that impact semantics in HLSL.
However, the document should be updated to highlight key differences and
unique considerations for Vulkan/SPIR-V targets over time.

## Motivation

Semantics and shader parameter access/passing/linking are not defined well
enough in existing
[HLSL Semantics documentation](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-semantics)
to use as a clear guide for implementation in a new compiler.

The DXIL specification section on
[Shader Parameters and Signatures](https://github.com/microsoft/DirectXShaderCompiler/blob/main/docs/DXIL.rst#shader-parameters-and-signatures)
provides some good detail on how parameters are mapped to DXIL constructs, but
does not cover all the related HLSL language features.

This document is meant to demystify this area of the language for the
implementation plan, and provide a background for discussing any proposed
adjustments to the HLSL language. It is also meant to provide a clear bridge
between HLSL language features and their mapping to DXIL constructs.

## HLSL Syntax

The following is a rough syntax, HLSL spec will need to be updated with
the exact syntax, then this can be updated to match.

Variable/field/parameter declaration semantics:

```syntax
declaration ::= [storage-class] [type-modifier]
                type name [array-defs]
                [: semantic] [= init-value]
```

Function return semantics:

```syntax
function-declaration ::= [function-attributes]
                         type name '(' parameter-list ')' [array-defs]
                         [: semantic] [function-body]
```

Semantics are allowed on decls of the following types:

- variable decls (local or global).
- field decls, where the syntax collides with a subset of bitfield syntax in C++
  where you specify the bit width using an identifier instead of a constant
  integer.
- parameter decls
- function decls - located after parameter list, before function body, and
  applies to the return value.

At the fundamental syntax level, semantics are just a way to tag a declaration
with an additional identifier. This identifier can indicate a special meaning
when this decl is used in certain contexts for certain targets, but at the basic
language level, semantics have no local impact on the meaning of a declaration.
Semantic identifiers are not captured into any naming scope visible to any HLSL
code. No local rules are applied to the identifier, such as uniqueness or naming
conventions, except when being used in a certain context with an appropriate
compilation target.

> Note: HLSL syntax allows multiple semantics to be specified on a single
> declaration, with repeated `: semantic` syntax.
> Only the last semantic defined will be used (`: semantic_ignored : semantic_used`).
> We should consider deprecating this behavior to avoid confusion.
>
> [Examples - Multiple Semantics on Same Declaration](#examples---multiple-semantics-on-same-declaration)

## Ignored semantics

Depending on the context of a declaration, semantics may be ignored. Semantics
that are used (not ignored) are called [Active semantics](#active-semantics) in
this document.

Semantics on global variable declarations are ignored by DXC.

> Historically, semantics on globals were exposed through the D3DXEffects
> framework, used with effects binaries compiled with FXC using `fx_*` target.
> The D3DXEffects framework is deprecated and has not been maintained or updated
> since around the D3D11 time frame.
> Support for compiling effects was never added to DXC.
> This document will not explore semantics for effects.

Semantics on local variables are ignored.

Semantics on functions and function parameters are ignored, except for active
shader entry functions that use semantics.

Semantics on fields in structures are also ignored, unless they are used in
parameters or return types, without having been overridden by a semantic on a
containing decl, for active shader entry functions that use semantics.

Ignored semantics have no rules applied, other than the basic identifier syntax.

## Active semantics

The remaining, current use for semantics discussed here is for identifying and
linking shader inputs and outputs. Different shader models and entry function
types have different rules for shader parameters and semantics.

Shader types can be categorized into several pipeline buckets to simplify
reasoning about the use of semantics within each pipeline:

| Pipeline | Shader types | Uses Semantics |
| --- | --- | --- |
| Graphics | `vertex`, `pixel`, `geometry`, `hull`, `domain` | Yes |
| Compute | `compute` | Yes |
| Mesh | `amplification`, `mesh`, `pixel`\* | Yes |
| Raytracing | `raygeneration`, `intersection`, `anyhit`, `closesthit`, `miss` | No |
| Work Graphs | `node` | Special case\*\* |

> \* `pixel` is also listed under Mesh, since `mesh` shaders feed the
> rasterizer, and thus `pixel` shaders in this pipeline.
>
> \*\* `node` shaders ignore semantics, except for one special case:
> `SV_DispatchGrid` on a broadcasting launch input record field when static grid
> size is not specified.

Where semantics are used:

- They will be parsed and split into a semantic name and an optional trailing
  semantic index.
  - `Semantic123` -> name: `Semantic`, index: `123`
  - `Semantic123Name5` -> name: `Semantic123Name`, index: `5`
- The semantic index defaults to zero if a trailing index is not present
  - `Semantic` -> name: `Semantic`, index: `0`
  - `Semantic123Name` -> name: `Semantic123Name`, index: `0`
- Semantic names beginning with `SV_` identify "*System Values*" which link to
  special values in the pipeline.
  - `SV_Position`, `SV_Target3`
- Semantic names not beginning with `SV_` are "user" or "arbitrary" semantics,
  which are used to identify user data passed through the pipeline from one
  stage to another that carries no special meaning to the pipeline.
- Arbitrary semantics have a maximum length of 64 characters, matched between
  pipeline stages as case-insensitive ASCII.
- Use of an unrecognized name starting with `SV_` will produce an error.
- Use of a recognized system value name on a shader parameter in the wrong
  location will produce an error.
- There are a few system values that are allowed in places where they don't have
  a special meaning for the pipeline, where they are interpreted as user
  semantics instead. This was originally meant to allow easier sharing of
  structures of attributes between locations that may use the system value with
  others that don't.
- For some shader parameter locations, certain system values may or may not
  actually attach to special values in the pipeline, depending on the setup of
  the stages in the pipeline. For instance, `SV_Position` output from a `vertex`
  shader only has special meaning if the next stage is the rasterizer, otherwise
  it's just user data passed to the next stage.

More details on some of these points for specific contexts will be expanded later.

### Legacy Semantics

A certain set of semantic names used in DX9-era HLSL can be mapped to equivalent
DX10+ system value semantics (`SV_*`), when using the `/Gec` (enable
compatibility) flag in DXC or FXC. This compatibility flag will only trigger
certain mappings when the legacy semantic is used in a context where the
equivalent system value is accepted.

However, this feature is deprecated and unavailable in HLSL 2021 and newer, so
this document will not cover this legacy semantic translation.

## Signature Element Translation

This section covers the general rules for translating types into signature
elements. Where these types come from, is dependent on the shader entry type,
and will be covered later.

Generally, shaders use sets of signature elements to define inputs and outputs.
Shader signatures describe the attribute values passed between shader stages or
between a shader stage and some fixed function part of the pipeline. For some
shader types, there are multiple input signatures or multiple output signatures,
separating different types of inputs or outputs. Some special system value
elements are not included in a shader signature, but types are still translated
into an element shape using the same rules described below.

One signature element is constructed from a single declaration of a numeric
scalar, vector, or matrix, or an array of one of these shapes. The shape of the
signature element is derived from the type of the declaration. Signature
elements are made up of vectors of up to 4 components (regardless of scalar
type), and consist of one or more rows. Signature elements with more than one
row are considered to be dynamically indexable on the row dimension.

Each signature element has a single semantic name assigned, as well as one
semantic index assignment per row in the signature element. For types not
involving structures, the semantic indexes will be a contiguous range of
indices.

### Basic Parameters and Return Types

Entry functions targeting stages like `vertex`, `pixel`, and `compute` use
ordinary function parameter declarations and return type to define shader inputs
and/or outputs.

Inputs and outputs are gathered separately, and `inout` parameters contribute to
both input and output gathering. Elements from the return type precede elements
from output parameters in the signature element ordering, and input or output
elements from parameters follow the order of parameters in the function
declaration.

[Examples - Basic Parameters and Return Types](#examples---basic-parameters-and-return-types)

### Basic Arrays

Array elements are stored on separate rows, and multi-dimensional arrays are
flattened into a single dimension for the final signature element shape (eg.
`float2[2][3]` -> `float2[6]`, shape: 6 rows by 2 columns).

[Examples - Basic Arrays](#examples---basic-arrays)

### Matrix Types

Matrix types are treated as arrays of vectors in the signature element, where
each vector is a row for a `row_major` matrix or a column for a `column_major`
matrix. In HLSL, matrices are logically `row_major`, and are indexed first by
row, just as if it is an array of row vectors. For a `column_major` matrix, this
logical HLSL row-based indexing will index into signature element columns
instead of rows.

Since matrix storage rows are treated just like array elements, each matrix row
(for `row_major`) or column (for `column_major`) will get its own semantic
index.

[Examples - Matrix Types](#examples---matrix-types)

### Matrix Arrays

An array of matrices is treated as an array of arrays of
vectors, where the outer array is the array of matrices, and the inner array is
the array of rows (or columns) for each matrix.

[Examples - Matrix Arrays](#examples---matrix-arrays)

### Structure Types

> TBD: This section needs revision and integration into the Struct fields section above.

When signature elements are gathered from a structure type, each field in the
structure will be turned into a separate signature element. This applies
recursively to fields of structure types. The order of signature elements will
follow the order of fields in the structure and contained structures,
recursively.

[Examples - Structure Types](#examples---structure-types)

### Struct Arrays

For arrays of a struct type, and/or array fields, array dimensions on types
containing a field will be gathered along with any array dimensions on the field
type itself. All of these array dimensions contribute to the final flattened
array sizes for the corresponding signature elements.

With structures, semantic index assignments may not be contiguous, as the index
assignment follows original data layout ordering for the top-level type from
which signature elements are gathered.

[Examples - Struct Arrays](#examples---struct-arrays)

### Special Parameters and Objects

> TBD: Cover special parameters like GS input arrays, MS output arrays, and
> special objects like GS streams, HS/DS patches, and Work Graph objects.

[Examples - Special Parameters and Objects](#examples---special-parameters-and-objects)

## Semantic Assignment

A semantic on a declaration used to gather signature elements will apply to all
signature elements gathered from that declaration, overriding any semantics on
fields inside the declaration type. Each signature element will get the same
semantic name, and the semantic indices assigned to each element row will be
determined by the original data layout ordering of the declaration type from
which the semantic is applied. Indices are assigned starting from the semantic
index specified on the outer-most declaration, and incrementing for each
subsequent element row assigned by the semantic on the same declaration.

Since a semantic declaration includes an index, even if it's an implicit zero,
this defines the starting index for this declaration and any contained elements
gathered from the same declaration. If this declaration is contained within an
array, it leads to multiple elements with the same starting index.

Only array dimensions for the declaration with the active semantic and arrays
contained within are accounted for when incrementing the semantic index. Array
dimensions on declarations containing this declaration are not counted, and lead
to multiple elements with the same semantic and starting index.

> TBD: examples of semantic assignment rules

When gathering signature elements from a declaration, the semantic name and
indices assigned to each interpreted signature element is determined by the
outer-most semantic found either on the declaration, or on any field declaration
down to the leaf field that corresponds to one element.

The semantic index for each element row is determined by the original data
layout ordering of the type from which the signature elements are gathered,
starting at the semantic index specified on the outer-most declaration, and
incrementing for each subsequent element row assigned by the semantic on the
same declaration.

### Semantics on struct fields

A set of different input or output semantics can be grouped into a single
parameter declaration or return type by using semantics on struct fields. In
this case, the semantic may be omitted on the parameter or function itself, and
the semantics on the fields will be used instead to construct separate signature
elements.

Examples:

```hlsl
struct VSIn {
  float4 pos : POSITION;
  float2 uv : TEXCOORD0;
};
struct VSOut {
  float4 pos : SV_Position;
  float2 uv : TEXCOORD0;
};

[shader("vertex")]
VSOut VSMain(VSIn input) { ... }
```

#### Semantic override

> TBD: Rework redundancy with parent section

In some cases, it may be necessary to override the semantic assigned to a struct
field. This can be done by explicitly specifying a different semantic on the
parameter or function declaration. This semantic name will apply to all fields
contained in the struct type, overriding any semantics on the fields themselves.
Each field will be assigned a set of semantic indices based on the next index
and leaf-value ordering in the data layout.

[Examples - Semantic override](#examples---semantic-override)

## Gathering Signature Elements

Signature elements are gathered from shader entry function return type,
parameters, and in some cases, from template type arguments of special object
parameters. The allowed locations and special object types depend on shader
type.

### Signature Points

Elements are grouped into different signature points depending on shader type.
Each shader kind has its own set of rules for mapping parameters or return types
to signature points. Some signature points group elements into an input or
output signature, which describes the elements of a buffer passed between
stages, while others just gather elements for special system values that are not
part of any signature. Some system values may be generated or consumed without
requiring space in any inter-stage parameter buffer. If the signature point has
an associated signature, these may either be excluded from the signature
entirely (using special ops for access), or included in the signature but have
no allocated location in the buffer (using standard signature ops for access).

This table lists all Signature Points and their associated Shader Kind, Packing
Kind, and Signature Kind:

| SigPoint | ShaderKind    | PackingKind    | SignatureKind    | Source                                     |
| -------- | ------------- | -------------- | ---------------- | ------------------------------------------ |
| VSIn     | Vertex        | InputAssembler | Input            | `in` params                                |
| VSOut    | Vertex        | Vertex         | Output           | return type and `out` params               |
| PCIn     | Hull          | None           | Invalid          | pc func `in` params                        |
| HSIn     | Hull          | None           | Invalid          | `in` params                                |
| HSCPIn   | Hull          | Vertex         | Input            | `InputPatch<T>` param                      |
| HSCPOut  | Hull          | Vertex         | Output           | main return type only                      |
| PCOut    | Hull          | PatchConstant  | PatchConstOrPrim | pc func `out` params                       |
| DSIn     | Domain        | PatchConstant  | PatchConstOrPrim | `in` params                                |
| DSCPIn   | Domain        | Vertex         | Input            | `OutputPatch<T>` param                     |
| DSOut    | Domain        | Vertex         | Output           | return type and `out` params               |
| GSVIn    | Geometry      | Vertex         | Input            | `in (point\|(line\|triangle)[_adj])` param |
| GSIn     | Geometry      | None           | Invalid          | `in` params                                |
| GSOut    | Geometry      | Vertex         | Output           | `(Point\|Line\|Triangle)Sream<T>` param    |
| PSIn     | Pixel         | Vertex         | Input            | `in` params                                |
| PSOut    | Pixel         | Target         | Output           | return type and `out` params               |
| CSIn     | Compute       | None           | Invalid          | `in` params                                |
| MSIn     | Mesh          | None           | Invalid          | `in` params                                |
| MSOut    | Mesh          | Vertex         | Output           | `out vertices` param                       |
| MSPOut   | Mesh          | Vertex         | PatchConstOrPrim | `out primitives` param                     |
| ASIn     | Amplification | None           | Invalid          | `in` params                                |

Some abbreviations used in the SigPoint names:

- First two letters = abbreviated Shader Kind (VS/PS/GS/HS/DS/CS/MS/AS), plus PC
  for the patch constant function for hull shaders
- PCIn/PCOut = Patch Constant Input/Output
- HSCPIn/DSCPIn/HSCPOut = Hull/Domain Shader Control Point Input/Output
- GSVIn = Geometry Shader Vertex Input
- MSPOut = Mesh Shader Primitive Output

There are several key patterns for collecting elements from parameters and
return types for different signature points:

- Ordinary `in` parameters correspond to input signature for `vertex` and
  `pixel` shaders
- Ordinary `in` parameters only specify system value elements loaded using
  special intrinsics for `hull` (and its patch constant function), `domain`,
  `geometry`, `compute`, `mesh` and `amplification` shaders.
- Ordinary `out` parameters and return type correspond to output signature for
  `vertex`, `pixel`, and `domain` shaders
- `inout` parameters are equivalent to an `in` and `out` parameter pair, and
  contribute to both input and output gathering.
- Parameters without `in`, `out`, or `inout` modifiers are considered `in`
  parameters.
- Special object parameters correspond to input/output signatures for
  tessellation and geometry shaders. For each of these special object
  parameters, the type argument `T` is used to define all signature elements for
  the signature. Only one parameter of that special object type is allowed for
  the entry point. For hull shaders, all control point elements are gathered
  from the return type only.
- `GSIn`, `MSOut`, and `MSPOut` require a single parameter that defines an
  entire signature, which is usually an array, but not required to be an array
  if there is only one element. The array dimension corresponds to the input
  vertex count for `GSIn` based on the primitive type, the maximum output vertex
  count for `MSOut`, and the maximum output primitive count for `MSPOut`.

For each signature point, there's an interpretation for each system value
semantic (and "Arbitrary" for user-defined semantics) that determines whether
it's allowed and how it's interpreted when used at that signature point.

This table lists the interpretation types used in later tables.

| Interpretation | Description                                                                       |
| -------------- | --------------------------------------------------------------------------------- |
| NA             | Not Allowed at this signature point                                               |
| SV             | Normal System Value                                                               |
| SGV            | System Generated Value (sorted last)                                              |
| Arb            | Treated as Arbitrary                                                              |
| NotInSig       | Not included in signature (special intrinsic)                                     |
| NotPacked      | Included in signature, but does not contribute to packing                         |
| Target         | Special handling for SV_Target                                                    |
| TessFactor     | Special handling for tessellation factors                                         |
| Shadow         | Shadow element must be added to a signature for compatibility (special intrinsic) |
| ClipCull       | Special packing rules for SV_ClipDistance or SV_CullDistance                      |

Most interpretations use standard LoadInput/StoreOutput/etc DXIL operations used
for all elements of a particular signature type in that shader stage. Some
system values use special intrinsics instead, as noted by the "NotInSig" and
"Shadow" interpretations. "NotPacked" still uses the standard signature access
intrinsics, but has no assigned packing location in a an inter-stage attribute
block.

The following tables are Semantic interpretations for each Signature Point,
grouped by shader stage. For each table, unlisted system values are disallowed
at all signature points in the table.

> Note: SM6_1, SM6_4 etc. indicate the minimum shader model that supports the
> system value at that signature point. A minimum shader model may be required
> for a particular shader stage, but this is not indicated here.

#### Vertex Shader

| Semantic               | VSIn           | VSOut    |
| ---------------------- | -------------- | -------- |
| Arbitrary              | Arb            | Arb      |
| VertexID               | SV             | NA       |
| InstanceID             | SV             | Arb      |
| Position               | Arb            | SV       |
| RenderTargetArrayIndex | Arb            | SV       |
| ViewPortArrayIndex     | Arb            | SV       |
| ClipDistance           | Arb            | ClipCull |
| CullDistance           | Arb            | ClipCull |
| ViewID                 | NotInSig SM6_1 | NA       |
| ShadingRate            | NA             | SV SM6_4 |
| StartVertexLocation    | NotInSig SM6_8 | NA       |
| StartInstanceLocation  | NotInSig SM6_8 | NA       |

- `VSIn` gathers from all `in` (and `inout`) parameters for the `Input`
  signature.
- `VSOut` gathers from the return type and all `out` (and `inout`) parameters
  for the `Output` signature.

SigPoint element gathering locations for vertex shader:

```hlsl
[shader("vertex")]
type VSMain(
  [in] type name, // VSIn
  out type name, // VSOut
  inout type name // both VSIn and VSOut
) // VSOut (returned type, if not void)
{ ... }
```

#### Pixel Shader

| Semantic               | PSIn            | PSOut           |
| ---------------------- | --------------- | --------------- |
| Arbitrary              | Arb             | NA              |
| InstanceID             | Arb             | NA              |
| Position               | SV              | NA              |
| RenderTargetArrayIndex | SV              | NA              |
| ViewPortArrayIndex     | SV              | NA              |
| ClipDistance           | ClipCull        | NA              |
| CullDistance           | ClipCull        | NA              |
| PrimitiveID            | SGV             | NA              |
| SampleIndex            | Shadow SM4_1    | NA              |
| IsFrontFace            | SGV             | NA              |
| Coverage               | NotInSig SM5_0  | NotPacked SM4_1 |
| InnerCoverage          | NotInSig SM5_0  | NA              |
| Target                 | NA              | Target          |
| Depth                  | NA              | NotPacked       |
| DepthLessEqual         | NA              | NotPacked SM5_0 |
| DepthGreaterEqual      | NA              | NotPacked SM5_0 |
| StencilRef             | NA              | NotPacked SM5_0 |
| ViewID                 | NotInSig SM6_1  | NA              |
| Barycentrics           | NotPacked SM6_1 | NA              |
| ShadingRate            | SV SM6_4        | NA              |
| CullPrimitive          | NotInSig        | NA              |

- `PSIn` gathers from all `in` and `inout` parameters for the `Input` signature.
- `PSOut` gathers from the return type and all `out` and `inout` parameters for
  the `Output` signature.

SigPoint element gathering locations for pixel shader:

```hlsl
[shader("pixel")]
type PSMain(
  [in] type name, // PSIn SigPoint
  out type name, // PSOut SigPoint
  inout type name // both PSIn and PSOut SigPoints
) // PSOut SigPoint (returned type, if not void)
{ ... }
```

#### Geometry Shader

| Semantic               | GSVIn    | GSIn           | GSOut    |
| ---------------------- | -------- | -------------- | -------- |
| Arbitrary              | Arb      | NA             | Arb      |
| InstanceID             | Arb      | NA             | Arb      |
| Position               | SV       | NA             | SV       |
| RenderTargetArrayIndex | SV       | NA             | SV       |
| ViewPortArrayIndex     | SV       | NA             | SV       |
| ClipDistance           | ClipCull | NA             | ClipCull |
| CullDistance           | ClipCull | NA             | ClipCull |
| PrimitiveID            | NA       | Shadow         | SGV      |
| GSInstanceID           | NA       | NotInSig       | NA       |
| IsFrontFace            | NA       | NA             | SGV      |
| ViewID                 | NA       | NotInSig SM6_1 | NA       |
| ShadingRate            | SV SM6_4 | NA             | SV SM6_4 |

- `GSIn` gathers from all `in` parameters.
- `GSVIn` uses the type of an input parameter with modifier
  `point|line|triangle|lineadj|triangleadj` to gather all input elements for the
  `Input` signature.
  - The array dimension (used for all but `point`) corresponds to the input
    vertex count based on the primitive type, and does not contribute to the
    shape of gathered signature elements.
- `GSOut` uses a special stream output `inout` object parameter to gather all
  output elements from the template type argument for the `Output` signature.
  Stream out objects: `PointStream<T>`, `LineStream<T>`, `TriangleStream<T>`.

SigPoint element gathering locations for geometry shader:

```hlsl
struct GSOut {
  // GSOut SigPoint fields
};
struct GSVIn {
  // GSVIn SigPoint fields
};

[shader("geometry")]
void GSMain(
  [in] type name, // GSIn SigPoint
  [in] <point|line|triangle|lineadj|triangleadj> GSVIn inputVertices[<vertex-count>],
  inout <Point|Line|Triangle>Stream<GSOut> outputStream
) { ... }
```

#### Hull Shader

Hull shader includes a patch constant function which also contributes to the
available signature points.

| Semantic               | PCIn           | HSIn           | HSCPIn   | HSCPOut  | PCOut      |
| ---------------------- | -------------- | -------------- | -------- | -------- | ---------- |
| Arbitrary              | NA             | NA             | Arb      | Arb      | Arb        |
| InstanceID             | NA             | NA             | Arb      | Arb      | NA         |
| Position               | NA             | NA             | SV       | SV       | Arb        |
| RenderTargetArrayIndex | NA             | NA             | SV       | SV       | Arb        |
| ViewPortArrayIndex     | NA             | NA             | SV       | SV       | Arb        |
| ClipDistance           | NA             | NA             | ClipCull | ClipCull | Arb        |
| CullDistance           | NA             | NA             | ClipCull | ClipCull | Arb        |
| OutputControlPointID   | NA             | NotInSig       | NA       | NA       | NA         |
| PrimitiveID            | NotInSig       | NotInSig       | NA       | NA       | NA         |
| TessFactor             | NA             | NA             | NA       | NA       | TessFactor |
| InsideTessFactor       | NA             | NA             | NA       | NA       | TessFactor |
| ViewID                 | NotInSig SM6_1 | NotInSig SM6_1 | NA       | NA       | NA         |
| ShadingRate            | NA             | NA             | SV SM6_4 | SV SM6_4 | NA         |

- `PCIn` gathers from all `in` parameters of the patch constant function.
- `HSIn` gathers from all `in` parameters of the hull shader main function.
- `HSCPIn` uses the type of the `InputPatch<T>` parameter to gather all control
  point input elements.
- `HSCPOut` uses the return type of the hull shader main function to gather all
  control point output elements.
- `PCOut` gathers from the return type and all `out` and `inout` parameters of
  the patch constant function for the `PatchConstOrPrim` signature.

The patch constant function can accept the `InputPatch<T,...>` and
`OutputPatch<T,...>` parameters as inputs (read-only) to access input and output
control point data.  These types must match the types used for the hull shader's
`InputPatch<T,...>` and return type respectively.

For Hull Shader stage, the `PatchConstOrPrim` signature is an output signature.

SigPoint element gathering locations for passthrough hull shader:

```hlsl
struct HSCPIn {
  // HSCPIn SigPoint fields
};
struct HSCPOut {
  // HSCPOut SigPoint fields
};

void PCPatchConstFunc(
  [in] type name, // PCIn SigPoint
  out type name, // PCOut SigPoint
  // Optionally, must match type in Hull Shader main function:
  [in] InputPatch<HSCPIn, <num-vertices>> inputPatch,
  [in] OutputPatch<HSCPOut, <num-vertices>> outputPatch
) { ... }

[shader("hull")]
[patchconstantfunc("PCPatchConstFunc")]
[...]
HSCPOut HSMain(
  [in] type name, // HSIn SigPoint
  [in] InputPatch<HSCPIn, <num-vertices>> inputPatch,
) { ... }
```

A special case for a passthrough hull shader is written in HLSL as the entry
point accepting parameter `InputPatch<T,...>` and `SV_OutputControlPointID`,
with return type `T`, then only returning the input control point indexed using
`SV_OutputControlPointID`. The control point function still needs to be defined,
and can be any legal control point shader. The result is DXIL that has a null
hull shader function, and a non-null patch constant function.

[Examples - Passthrough HS](#examples---passthrough-hs)

#### Domain Shader

| Semantic               | DSIn           | DSCPIn   | DSOut    |
| ---------------------- | -------------- | -------- | -------- |
| Arbitrary              | Arb            | Arb      | Arb      |
| InstanceID             | NA             | Arb      | Arb      |
| Position               | Arb            | SV       | SV       |
| RenderTargetArrayIndex | Arb            | SV       | SV       |
| ViewPortArrayIndex     | Arb            | SV       | SV       |
| ClipDistance           | Arb            | ClipCull | ClipCull |
| CullDistance           | Arb            | ClipCull | ClipCull |
| DomainLocation         | NotInSig       | NA       | NA       |
| PrimitiveID            | NotInSig       | NA       | NA       |
| TessFactor             | TessFactor     | NA       | NA       |
| InsideTessFactor       | TessFactor     | NA       | NA       |
| ViewID                 | NotInSig SM6_1 | NA       | NA       |
| ShadingRate            | NA             | SV SM6_4 | SV SM6_4 |

- `DSIn` gathers from all `in` parameters for the `PatchConstOrPrim` signature.
- `DSCPIn` uses the type `T` of the `OutputPatch<T,...>` parameter to gather all
  control point elements for the `Input` Signature.
- `DSOut` gathers from the return type and all `out` and `inout` parameters for
  the `Output` signature.

For Domain Shader stage, the `PatchConstOrPrim` signature is an input signature.

SigPoint element gathering locations for domain shader:

```hlsl
struct DSCPIn {
  // DSCPIn SigPoint fields
};
[shader("domain")]
void DSMain(
  [in] type name, // DSIn SigPoint
  [in] OutputPatch<DSCPIn, <num-vertices>> controlPointData,
  out type name // DSOut SigPoint
) { ... }
```

> TBD: try `inout` parameters (odd since in should be from patch constant sig
>   DSIn, and out is vertex output signature DSOut)

#### Compute, Mesh, and Amplification Shaders

| Semantic               | CSIn     | MSIn     | MSOut    | MSPOut    | ASIn     |
| ---------------------- | -------- | -------- | -------- | --------- | -------- |
| Arbitrary              | NA       | NA       | Arb      | Arb       | NA       |
| Position               | NA       | NA       | SV       | NA        | NA       |
| RenderTargetArrayIndex | NA       | NA       | NA       | SV        | NA       |
| ViewPortArrayIndex     | NA       | NA       | NA       | SV        | NA       |
| ClipDistance           | NA       | NA       | ClipCull | NA        | NA       |
| CullDistance           | NA       | NA       | ClipCull | NA        | NA       |
| PrimitiveID            | NA       | NA       | NA       | SV        | NA       |
| DispatchThreadID       | NotInSig | NotInSig | NA       | NA        | NotInSig |
| GroupID                | NotInSig | NotInSig | NA       | NA        | NotInSig |
| GroupIndex             | NotInSig | NotInSig | NA       | NA        | NotInSig |
| GroupThreadID          | NotInSig | NotInSig | NA       | NA        | NotInSig |
| ViewID                 | NA       | NotInSig | NA       | NA        | NA       |
| ShadingRate            | NA       | NA       | NA       | SV        | NA       |
| CullPrimitive          | NA       | NA       | NA       | NotPacked | NA       |

SigPoint element gathering locations for compute shader:

```hlsl
[shader("compute")]
void CSMain(
  [in] type name, // CSIn SigPoint
) { ... }
```

SigPoint element gathering locations for mesh shader:

```hlsl
[shader("mesh")]
void MSMain(
  [in] type name, // MSIn SigPoint
  out vertices type name, // MSOut SigPoint
  out primitives type name, // MSPOut SigPoint
  out indices uint3 name, // not gathered for any SigPoint
) { ... }
```

SigPoint element gathering locations for amplification shader:

```hlsl
[shader("amplification")]
void ASMain(
  [in] type name, // ASIn SigPoint
) { ... }
```

#### Node Shaders

Node shaders (Work Graphs) accept the same input system semantics as compute
shaders, with additional constraints based on launch mode. However, they do not
have specific associated signature points.

> TBD: table of allowed system values for node shader input system values based on
> launch mode

They also have special object parameters for input and output nodes and records.
These object parameters do not have semantics, but their template type parameter
specifies a record type.

> TBD: outline special object parameter types

The record type may contain one field with the `SV_DispatchGrid` semantic, which
is used to specify a dispatch grid for a broadcasting launch when static grid
size is not specified.

[Examples - Node Shader](#examples---node-shader)

#### Raytracing Shaders

Raytracing does not make any use of semantics for inputs or outputs, and instead
use payload and attribute structures with standard data layouts. Thus raytracing
shaders are not covered in this document.

### System Value Constraints

Type constraints are applied anywhere the semantic is interpreted as a system
value, rather than an arbitrary semantic (`Arb`). In DXIL, an enumeration value
is used to identify the system value, when it is interpreted as such, separate
from the string name.

| Semantic                                   | sem. Index | Allowed Types                           |
| ------------------------------------------ | ---------- | --------------------------------------- |
| VertexID                                   | 0          | up to 32-bit int/uint                   |
| InstanceID                                 | 0          | up to 32-bit int/uint                   |
| Position                                   | 0          | vec4 of up to 32-bit float              |
| RenderTargetArrayIndex, ViewPortArrayIndex | 0          | up to 32-bit int/uint                   |
| ClipDistance, CullDistance                 | any        | See: *clip/cull*                        |
| OutputControlPointID                       | 0          | int/uint                                |
| DomainLocation                             | 0          | See: *DomainLocation*                   |
| PrimitiveID                                | 0          | up to 32-bit int/uint                   |
| GSInstanceID                               | 0          | up to 32-bit int/uint                   |
| SampleIndex                                | 0          | up to 32-bit int/uint                   |
| IsFrontFace                                | 0          | int/uint (interpreted as `bool`)        |
| Coverage, InnerCoverage                    | 0          | int/uint; mutually exclusive for `PSIn` |
| Target                                     | 0-7        | See: *Target*                           |
| Depth, DepthLessEqual, DepthGreaterEqual   | 0          | up to 32-bit float; mutually exclusive  |
| StencilRef                                 | 0          | up to 32-bit int/uint                   |
| DispatchThreadID, GroupID, GroupThreadID   | 0          | up to vec3 of int/uint                  |
| GroupIndex                                 | 0          | int/uint                                |
| TessFactor                                 | 0          | See: *TessFactor*                       |
| InsideTessFactor                           | 0          | See: *InsideTessFactor*                 |
| ViewID                                     | 0          | int/uint                                |
| Barycentrics                               | 0          | vec3 of up to 32-bit float              |
| ShadingRate                                | 0          | up to 32-bit int/uint                   |
| CullPrimitive                              | 0          | bool                                    |
| StartVertexLocation, StartInstanceLocation | 0          | int/uint                                |
| DispatchGrid                               | 0          | up to vec3 of up to 32-bit int/uint     |

Key:

- "up to vec4": scalar or vector up to 4 components.
- "array size 2": the element must be an array of size 2.
- "up to float4": scalar or vector of up to 4 components, consisting of 32-bit
  `float` values.
- "up to 32-bit float": `half`/`float16_t`, `min16float`, or 32-bit `float`.
- "up to 32-bit int": `int16_t`, `min16int`, or 32-bit `int`. DXIL: `i16` or
  `i32`.
- "int/uint": signed or unsigned 32-bit int, DXIL: `i32`.

Special cases:

- *clip/cull*: Any combinations of scalars/vectors combined into one or two
  vectors of up to 4 32-bit floats each, shared between `SV_ClipDistance` and
  `SV_CullDistance`.
- *DomainLocation*: up to float2 for `quad` domain; up to float3 for `tri` and
  `isoline` domains.
- *Target*: up to 8 rows of combined `SV_Target` outputs, each up to vec4 of up
  to 32-bit float; array allowed; non-overlapping semantic index; semantic index
  must match signature row.
- *TessFactor*: up to 32-bit int/uint of (per domain): `isoline`: array size 2;
  `tri`: array size 3; `quad`: array size 4
- *InsideTessFactor*: up to 32-bit int/uint of (based on domain): `tri`: single
  scalar; `quad`: array size 2; `isoline`: disallowed

### System Value Details

> TBD: Can individual system value details be described together adequately in
> the System Value Constraints section, or is additional description needed
> here?

> TBD: Expand on details for each system value.
>
> Include type/interpolation constraints, valid locations for different stages,
> and any special handling or notes.

Interpolation mode notes:

- Interpolation modes are generally only applicable to pixel shader inputs,
  though they can impact packing, so they should match in stages feeding
  the rasterizer to prevent packing mismatches.
- For integer types, interpolation mode must be `nointerpolation`. This is
  assumed with no declared interpolation mode on a signature element with
  integer component type.

#### VertexID

#### InstanceID

#### Position

#### RenderTargetArrayIndex and ViewPortArrayIndex

#### ClipDistance and CullDistance

#### OutputControlPointID

#### DomainLocation

#### PrimitiveID

#### GSInstanceID

#### SampleIndex

#### IsFrontFace

#### Coverage

#### InnerCoverage

#### Target

#### Depth

#### DepthLessEqual and DepthGreaterEqual

#### StencilRef

#### DispatchThreadID

#### GroupID

#### GroupIndex

#### GroupThreadID

#### TessFactor

#### InsideTessFactor

#### ViewID

#### Barycentrics

Pixel shader input only (`PSIn`). Does not contribute to packing, accessed with
special DXIL op.

Constraints:

- vec3 of up to 32-bit float
- `nointerpolation` not allowed

#### ShadingRate

#### CullPrimitive

#### StartVertexLocation and StartInstanceLocation

## DirectX and DXIL

### Shader Signatures and Attribute Space

In DirectX, Shaders that operate within the graphics pipeline may read and write
parameters provided from or to fixed function components of the pipeline or
other programmable shader stages. Data passed between shaders or certain fixed
function stages is collected and packed into an attribute block.  This attribute
block is a set of up to 32 vectors of 4 components each, where each component is
a 32-bit value representing a float, int, uint, or bool (0=false or
non-zero=true).

Shader signatures define how parameters are mapped into this attribute block.
Each signature consists of a set of signature elements, each with a semantic
name and one or more rows of up to 4 components each. Signature elements are
packed into the attribute block according to certain packing rules, which depend
on the kind of signature (input/output/patch constant/etc.) and the shader
stage.

Some shader parameters that are purely provided by or consumed by fixed function
parts of the pipeline do not use the attribute block for passing data, and
instead use special DXIL operations to read or write these values directly.
Some parameter types that have no direct connection to another shader may still
be included in the signature description, and may even be packed into the
attribute block, for historical compatibility reasons.

Parameters passed between shaders must be mapped to matching locations at the
connecting stages, to ensure that data is passed correctly. However, this only
applies to parameters (components) that are read by the consuming shader.

### Signature Packing Constraints

Many shader parameters defined in HLSL may not map perfectly to a set of
4-component vectors. Thus, packing is applied to better utilize the available
space in the attribute block.

However, rows of the attribute block can be optimized/remapped by the driver
based on parameter usage in the final combination of shaders and other pipeline
state information. Thus, certain constraints are placed on how parameters can be
packed into the attribute block, to ensure compatibility with driver remapping
optimizations.

While some hardware/drivers may be able to remap attributes at a scalar
granularity, rather than per-row, the constraints are defined to work at row
granularity for greater compatibility. This is the source of many of the packing
constraints that follow.

As far as the packing algorithm is concerned, there could be multiple
algorithms, depending on the needs of the application, as long as they provide
consistent locations for attributes between stages, and satisfy the constraints.
For DXC, a simple first-fit packing algorithm is used that scans through the
available rows in order, placing attributes in the first available space that
fits, while respecting the constraints. This algorithm is not optimal, but it
allows for a certain flexibility that is relied on in practice in DirectX
applications. This flexibility is the ability to guarantee packing compatibility
between the subsets of two structures as long as one of the structures is a
prefix of the other. This is called prefix-stable packing in DXC
(`-pack-prefix-stable`). DXC also provides a more optimal packing algorithm
(`-pack-optimized`), but signatures defined at connecting stages must match
exactly to guarantee compatibility.

> TBD: signature packing examples

#### Dynamic Indexing

Ranges of rows in the attribute block can be marked as dynamically indexable.
Blocks of dynamically indexable rows would need to be kept together
and in order, to allow for dynamic indexing to work correctly.

This places additional constraints on how attributes can be packed into these
rows. Mosts system values are not dynamically indexable, and thus may not be
packed into these dynamically indexable rows.

The only system values that are dynamically indexable are tessellation factors
(`SV_TessFactor` and `SV_InsideTessFactor`), which are only used in hull shaders
and domain shaders.

Whenever a parameter uses more than one row, it is considered to be dynamically
indexable, since a connecting shader stage could index it by row dynamically.
Otherwise packing might not match between a stage that does not dynamically
index it and one that does.  When a dynamically indexable parameter is packed
into the attribute block, all rows in the attribute block used for that
parameter are considered dynamically indexable.

Note: Due to the way DXIL separately defines and accesses signature elements,
dynamic indexing can be assumed to be constrained to within a particular
multi-row signature element. This means that the constraint inherited from the
original DXBC for dynamic indexing of inputs/outputs may not need to be as
strict for a pipeline consisting of only DXIL shaders. In other words, packing a
system value into the same row as a dynamically indexable element may not be a
problem for drivers in practice, since there's no risk of the system value being
dynamically indexed.

> TBD: dynamic indexing examples

#### Mixing non-32-bit types

Though the attributes in the attribute block are defined to be 32-bit values,
other types may be used in HLSL. These types will not impact the available
attribute space for packing, but the driver may use this information to optimize
the actual space needed and interpolation precision used for the attributes.
Since this would involve remapping of rows in the attribute block, there are
constraints on which types may be packed together.

Basically, as long as interpolation mode is the same, types in the the following
groupings can be packed together, but not mixed with other groupings:

- 32-bit types: `float`, `int`, `uint`, `bool`, plus types that map to these,
  like `half` (mapped to `float` in DXIL in min-precision mode), and 64-bit
  types that use two 32-bit uint components for the signature element, like
  `double`, `int64_t`, `uint64_t`.
- in min-precision mode (default): 16-bit min-precision types: `min16float`,
  `min16int`, `min16uint`, plus equivalent types that map to these in DXIL:
  `min10float`, `min12int`
- in native 16-bit type mode (`-enable-16bit-types`): 16-bit types: `half`,
  `float16_t`, `int16_t`, `uint16_t`, `half`

> TBD: examples of mixing types and impact on packing

#### Interpolation Modes

Each signature element has an interpolation mode associated with it, which
defines how the rasterizer will interpolate the attribute values across a
primitive when providing these values to the pixel shader.

Signature elements with different interpolation modes cannot be packed together,
since the interpolation behavior is specified on a per-row basis in the
attribute block.

In order to guarantee a matching packing layout between a stage that feeds the
rasterizer and a pixel shader that accesses the interpolated values, shaders
feeding the rasterizer should use the same interpolation modes as specified in
the pixel shader for the matching attribute. Otherwise, packing differences
could occur between the two shaders, leading to signature mismatches at runtime.

While the runtime doesn't enforce consistent interpolation modes between stages,
the differences that matter will be seen as packing location differences, which
are caught by the runtime signature validation.

Default interpolation modes are mostly assigned by type, with exceptions for
certain system values that deviate from the type-based defaults:

- All 32-bit or smaller floating point types default to `linear` interpolation
  mode
- All integer and boolean types default to `nointerpolation`, which is required,
  since they cannot be interpolated by the rasterizer.
- All 64-bit types default to `nointerpolation`, since they
  map to 32-bit uint components
- `SV_Position` defaults to `noperspective` (aka. linear noperspective)
- `SV_SampleIndex` shows as `nointerpolation` in the signature element, but it
  is not packed into the attribute block, and it uses a special intrinsic to
  load the value, so interpolation mode is not really used.
- TBD: other exceptions?

Example where interpolation modes impact packing:

```hlsl
struct PSIn {
  float2 uv0 : TEXCOORD0;               // linear (default for float2)
  noperspective float2 uv1 : TEXCOORD1; // noperspective
  // If the vertex shader omits the noperspective qualifier above,
  // packing will differ between the two shaders, because the differing
  // interpolation modes will force separate rows for uv0 and uv1 for the
  // pixel shader, but the vertex shader will not know about the differing
  // interpolation modes, so it will pack them together.
  // This would lead to a signature mismatch error at runtime.
};
float4 PSMain(PSIn In) : SV_Target {
  ...
}
```

### DXIL Signature Metadata

> TBD: DXIL module signature metadata details

### DXIL/DXBC Container Signature Parts

> TBD: container part details

## Vulkan and SPIR-V

> TBD: Vulkan/SPIR-V details, and differences from DirectX/DXIL.

## Examples

Input and output elements are listed for each example, showing the ordering of
elements packed into each signature. For each element, the semantic name is
followed by the semantic index list (eg. `[0,1,2]`) and the dimensions of each
element as (rows x columns).

Listed elements may not be included in a DXIL shader signature, depending on the
semantic interpretation for the signature point, such as how compute shaders
have no input signature describing their inputs in DXIL.

> TBD: many more examples needed, plus links to compiler explorer.

### Examples - Basic Parameters and Return Types

```hlsl
// Input elements: SV_DispatchThreadID [0] (1x3)
[shader("compute")]
[numthreads(64,1,1)]
void CSMain(uint3 dtid : SV_DispatchThreadID) { ... }

// Input elements: SV_Position [0] (1x4), MyInput [0] (1x1)
// Output elements: SV_Target [0] (1x4), SV_Depth [0] (1x1)
[shader("pixel")]
float4 PSMain(float4 pos : SV_Position,
              out float depth : SV_Depth,
              float input : MyInput
) : SV_Target { ... }

// 'inout' parameter contributes to both input and output elements
// Input elements: POSITION [0] (1x4), TEXCOORD [0] (1x2), TEXCOORD [1] (1x2)
// Output elements: SV_Position [0] (1x4), TEXCOORD [0] (1x2), TEXCOORD [1] (1x2)
[shader("vertex")]
float4 VSMain(float4 pos : POSITION,
              inout float2 t0 : TEXCOORD0,
              out float2 out_t1 : TEXCOORD1,
              float2 in_t1 : TEXCOORD1
) : SV_Position { ... }
```

### Examples - Basic Arrays

```hlsl
// Input elements: INOUT [0,1,2] (3x2), IN [3,4,5,6] (4x2)
// Output elements: RETURN [0,1] (2x4), INOUT [0,1,2] (3x2), OUT [3,4,5,6] (4x2)
[shader("vertex")]
float4 VSMain(inout float2 inout0[3] : INOUT0,
              out float2 out3[2][2] : OUT3,
              float2 in3[2][2] : IN3
)[2] : RETURN { ... }
// Note: array dimension [2] on return type is placed after the function parameter list.
```

### Examples - Matrix Types

> TBD: matrix examples, with special cases for one row/column, and orientation.

```hlsl
// Input elements: TEXCOORD [0,1,2] (3x2), TEXCOORD [3] (1x2)
// Output elements: RETURN [0] (1x2), TEXCOORD [1,2] (2x1)
[shader("vertex")]
float3x2 VSMain(float2x3 in_t0 : TEXCOORD0,
                float2x1 in_t3 : TEXCOORD3,
                out float2x1 out_t3 : TEXCOORD0,
                out float1x2 out_t4 : TEXCOORD1
) : RETURN { ... }
```

### Examples - Matrix Arrays

```hlsl
// Input elements: IN [0,1,2,3,4,5] (6x2), IN [6,7,8] (3x2)
// Output elements: RETURN [0,1,2,3] (4x3), OUT [0,1] (2x2), OUT [2,3,4,5] (4x1)
[shader("vertex")]
float3x2 VSMain(float2x3 in0[2] : IN0,
                float2x1 in6[3] : IN6,
                out float2x1 OUT0[2] : OUT0,
                out float1x2 OUT2[2] : OUT2
)[2] : RETURN { ... }
```

> TBD: more examples

### Examples - Structure Types

```hlsl
struct Base {
  float a : A;
  float2 b : B;
};
struct Derived : Base {
  int c : C;
};
struct Container {
  Derived d;
  float e : E;
};

// Input elements: A [0] (1x1), B [0] (1x2), C [0] (1x1), E [0] (1x1)
// Output elements: A [0] (1x1), B [0] (1x2), C [0] (1x1), E [0] (1x1)
[shader("vertex")]
void VSMain(
  Container CIn;,
  out Container COut,
) { ... }
```

> TBD: describe element layout for this example.

> TBD: more structure examples

### Examples - Struct Arrays

> TBD: structure with arrays examples

### Examples - Special Parameters and Objects

> TBD: special parameters and objects examples

### Examples - Semantic override

```hlsl
struct SomeStruct {
  float4 pos : Overridden;
};

[shader("vertex")]
SomeStruct VSMain(SomeStruct input : POSITION) : SV_Position { ... }
```

In this example, the `pos` field in `SomeStruct` would normally generate an
element with `Overridden` user semantic, but for the input, it has the
`POSITION` semantic, which will override it and generate a signature element
with the `POSITION` arbitrary user semantic instead. For the return type, the
`pos` field will generate a signature element with the `SV_Position` system
value semantic, due to that semantic being used on the function, which applies
to the return type.

### Examples - Multiple Semantics on Same Declaration

```hlsl
// SV_Ignored is ignored, since the last semantic takes precedence
// Input elements: SV_DispatchThreadID [0] (1x3)
[shader("compute")]
[numthreads(64,1,1)]
void CSMain(uint3 dtid  : SV_Ignored : SV_DispatchThreadID) { ... }
```

### Examples - Passthrough HS

### Examples - Node Shader

> TBD: node shader, including SV_DispatchGrid examples

## Quirks and Compatibility Notes

### Elements from nested fields

This example reveals differences in the way nested fields map to signature
elements between DXC and FXC:

```hlsl
struct PSIn {
  float a : A;
  float b : B;
};

// semantic `IN` overrides field semantics
float4 PSMain(PSIn In[2] : IN) : SV_Target {
  return float4(In[0].a, In[0].b, In[1].a, In[1].b);
}

// Code using packed elements is equivalent, but the signatures differ.

// DXC input signature:
// Name                 Index   Mask Register SysValue  Format   Used
// -------------------- ----- ------ -------- -------- ------- ------
// IN                       0   x           0     NONE   float   x
// IN                       1    y          0     NONE   float    y
// IN                       2   x           1     NONE   float   x
// IN                       3    y          1     NONE   float    y

// FXC input signature:
// Name                 Index   Mask Register SysValue  Format   Used
// -------------------- ----- ------ -------- -------- ------- ------
// IN                       0   xy          0     NONE   float   xy
// IN                       2   xy          1     NONE   float   xy

// It's like FXC merges fields that packed into the same register into a single element,
// while keeping the original semantic indices, while DXC always makes a separate
// element for each field.
```

This is a further complication of the above example, showing nested structures, and reveals even stranger behavior with FXC:

```hlsl
struct SubStruct {
  float c, d;
};

struct PSIn {
  float a : A;
  SubStruct b : B;
};

float4 PSMain(PSIn In[2] : IN) : SV_Target {
  return float4(In[0].a, In[0].b.c, In[1].a, In[1].b.d);
}
```
