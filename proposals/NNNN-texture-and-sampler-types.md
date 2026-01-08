---
title: "[NNNN] - Texture and Sampler Types"
params:
  authors:
    - s-perron: Steven Perron
  status: Under Consideration
  sponsors:
---

## Introduction

This proposal describes the design for implementing Texture and Sampler types in
Clang for HLSL, including their frontend representation, LLVM IR generation, and
testing strategy within the offload-test-suite.

The implementation of the Texture and Sampler types will be modeled after the
implementation of `Buffer` and `RWBuffer`. We will define a resource record type
for each resource type. It will contain a handle with the appropriate
attributes. The member functions for the class will be implemented as HLSL
builtin functions. The builtin functions will be translated to target-specific
intrinsics during codegen.

## Motivation

Texture resources (`Texture2D`, `Texture3D`, etc.) and Samplers
(`SamplerState`, `SamplerComparisonState`) are fundamental to graphics
programming in HLSL.

## Proposed solution

The design follows the pattern established for `Buffer` and `RWBuffer`. Textures
and Samplers will be defined as record types in the HLSL library. These records
will wrap an internal `__hlsl_resource_t` handle. Member functions will be
implemented as wrappers that call clang builtins, passing the underlying
resource handles.

This design will cover the implementation of:

* `Texture1D`
* `Texture2D`
* `Texture3D`
* `TextureCube`
* `Texture1DArray`
* `Texture2DArray`
* `TextureCubeArray`
* `Texture2DMS`
* `Texture2DMSArray`
* `RWTexture1D`
* `RWTexture2D`
* `RWTexture3D`
* `RWTexture1DArray`
* `RWTexture2DArray`
* `SamplerState`
* `SamplerComparisonState`

Many elements of the design will be the same as other resources or have already
been designed:

* Initialization and constructors: See [0025 - Resource Initialization and
  Constructors](0025-resource-initialization-and-constructors.md).
* Binding: See [0024 - Implicit Resource
  Binding](0024-implicit-resource-binding.md) and [0030 - Vulkan Resource
  Binding](0030-vulkan-resource-binding.md).
* Resource attributes: See [0015 - Mapping Resource Attributes to DXIL and
  SPIR-V](0015-resource-attributes-in-dxil-and-spirv.md).
* Target types: See [0018 - HLSL resources in
  SPIR-V](0018-spirv-resource-representation.md) and [0015 - Mapping Resource
  Attributes to DXIL and SPIR-V](0015-resource-attributes-in-dxil-and-spirv.md).

The detailed design in this proposal will fill in the details of the
`HLSLAttributedResourceType` for these types. It should follow the design in
[0006 - Resource Representations in Clang and
LLVM](0006-resource-representations.md).

To test the texture types, we will add new tests to the offload test suite.
There will be a test focusing on each member function separately. The tests will
provide different values as the parameters to ensure that they are correctly
used. However, we will not be testing every possible feature in the APIs. For
example, when testing the sampling functions, we will have two different
samplers. One will have the min filter to nearest, and mag filter set to linear.
The other sampler will have that swapped. Then we can sample the texture 4
times. For each sampler, we will sample first with a level of detail less than 0
and then with a level of detail greater than 0. This should be enough to prove
that the compiler is correctly picking the correct sampler and the correct level
of detail when doing the sample. We will also ensure we are using the correct
coordinates.

Note that we will not be using mipmapped textures. This makes the
description of the test in the offload test suite more complicated without
adding more test coverage. This turns into testing for the drivers and is best
left for the API's conformance tests.

## Detailed design

### Texture type in clang

#### The resource record type

Texture resources are represented in Clang using a record type defined in the
HLSL library. This record exposes the interface that the developer uses. Its
implementation contains a single member of type `__hlsl_resource_t`, annotated
with appropriate attributes to denote the specific resource kind (e.g.,
`Texture2D`, `TextureCube`) and element type.

The member functions are implemented as calls to HLSL builtin functions. These
builtins take the resource handle as the first parameter and forward the
remaining arguments.

When a member function requires a sampler (e.g., `Sample`), the `SamplerState`
object is passed to the member function. The implementation extracts the handle
from the `SamplerState` record and passes it to the underlying builtin.

For example, `Texture2D<float4>` would look effectively like:

```cpp
template <typename T>
class Texture2D {
  __hlsl_resource_t [[hlsl::resource_class(SRV)]]
                    [[hlsl::dimension(2D)]]
                    [[hlsl::contained_type(T)]]
                    [[hlsl::is_rov(false)]]
                    [[hlsl::is_multisample(false)]]
                    [[hlsl::is_array(false)]] Handle;

public:
  Texture2D() = default;

  // Sampling methods
  T Sample(SamplerState s, float2 location) {
    return __builtin_hlsl_resource_sample(Handle, s.Handle, location);
  }
  // ... other Sample overloads ...

  T SampleBias(SamplerState s, float2 location, float bias) {
    return __builtin_hlsl_resource_sample_bias(Handle, s.Handle, 
                                               location, bias);
  }
  // ... other SampleBias overloads ...

  T SampleGrad(SamplerState s, float2 location, 
               float2 ddX, float2 ddY) {
    return __builtin_hlsl_resource_sample_grad(Handle, s.Handle, 
                                               location, ddX, ddY);
  }
  // ... other SampleGrad overloads ...

  T SampleLevel(SamplerState s, float2 location, float lod) {
    return __builtin_hlsl_resource_sample_level(Handle, s.Handle, 
                                                location, lod);
  }
  // ... other SampleLevel overloads ...

  // Comparison Sampling
  float SampleCmp(SamplerComparisonState s, float2 location, 
                  float compare_value) {
    return __builtin_hlsl_resource_sample_cmp(Handle, s.Handle, 
                                              location, compare_value);
  }
  // ... other SampleCmp overloads ...

  float SampleCmpLevelZero(SamplerComparisonState s, float2 location, 
                           float compare_value) {
    return __builtin_hlsl_resource_sample_cmp_level_zero(Handle, 
                                                         s.Handle, 
                                                         location, 
                                                         compare_value);
  }
  // ... other SampleCmpLevelZero overloads ...

  // Load / Access
  T Load(int3 location) {
    return __builtin_hlsl_resource_load(Handle, location);
  }
  // ... other Load overloads ...

  // Implemented the same way as `Buffer`.
  const T& operator[](int2 pos) {
    return *__builtin_hlsl_resource_getpointer(Handle, pos);
  }

  // Gather
  float4 Gather(SamplerState s, float2 location) {
    return __builtin_hlsl_resource_gather(Handle, s.Handle, 
                                          location);
  }
  // ... other Gather overloads ...

  // Variants for Green, Blue, Alpha
  float4 GatherRed(SamplerState s, float2 location) {
      return __builtin_hlsl_resource_gather_red(Handle, s.Handle, 
                                                location);
  }
  // ...

  float4 GatherCmp(SamplerComparisonState s, float2 location, 
                             float compare_value) {
    return __builtin_hlsl_resource_gather_cmp(Handle, s.Handle, 
                                              location, compare_value);
  }
  // ... other GatherCmp overloads ...

  float4 GatherCmpRed(SamplerComparisonState s, float2 location, 
                                float compare_value) {
      return __builtin_hlsl_resource_gather_cmp_red(Handle, s.Handle, 
                                                    location, compare_value);
  }

  // Info
  void GetDimensions(out uint width, out uint height) {
      __builtin_hlsl_resource_getdimensions_xy(Handle, width, 
                                               height);
  }
  // ... other GetDimensions overloads ...

  float CalculateLevelOfDetail(SamplerState s, float2 location) {
      return __builtin_hlsl_resource_calculate_lod(Handle, s.Handle, 
                                                   location);
  }
}
```

#### Member functions

The following table lists the member functions and the texture types that support
them.

| Function | Supported Types | Description |
| :--- | :--- | :--- |
| `Sample` | `Texture1D`, `Texture1DArray`, `Texture2D`, `Texture2DArray`, `Texture3D`, `TextureCube`, `TextureCubeArray` | Samples the texture using a sampler. |
| `SampleBias` | `Texture1D`, `Texture1DArray`, `Texture2D`, `Texture2DArray`, `Texture3D`, `TextureCube`, `TextureCubeArray` | Samples the texture after applying a bias value to the mip level. |
| `SampleGrad` | `Texture1D`, `Texture1DArray`, `Texture2D`, `Texture2DArray`, `Texture3D`, `TextureCube`, `TextureCubeArray` | Samples the texture using gradients to influence the sample location calculation. |
| `SampleLevel` | `Texture1D`, `Texture1DArray`, `Texture2D`, `Texture2DArray`, `Texture3D`, `TextureCube`, `TextureCubeArray` | Samples the texture on the specified mip level. |
| `SampleCmp` | `Texture1D`, `Texture1DArray`, `Texture2D`, `Texture2DArray`, `TextureCube`, `TextureCubeArray` | Samples the texture and compares the result against a comparison value. |
| `SampleCmpLevelZero` | `Texture1D`, `Texture1DArray`, `Texture2D`, `Texture2DArray`, `TextureCube`, `TextureCubeArray` | Samples the texture (mip level 0 only) and compares the result against a comparison value. |
| `Load` | All `Texture*` and `RWTexture*` types | Reads texture data directly (texel fetch) without a sampler. |
| `Gather` | `Texture2D`, `Texture2DArray`, `TextureCube`, `TextureCubeArray` | Returns the four texels that would be used in a bilinear filtering operation. |
| `GatherRed` | `Texture2D`, `Texture2DArray`, `TextureCube`, `TextureCubeArray` | Returns the red component of the four texels that would be used in a bilinear filtering operation. |
| `GatherGreen` | `Texture2D`, `Texture2DArray`, `TextureCube`, `TextureCubeArray` | Returns the green component of the four texels that would be used in a bilinear filtering operation. |
| `GatherBlue` | `Texture2D`, `Texture2DArray`, `TextureCube`, `TextureCubeArray` | Returns the blue component of the four texels that would be used in a bilinear filtering operation. |
| `GatherAlpha` | `Texture2D`, `Texture2DArray`, `TextureCube`, `TextureCubeArray` | Returns the alpha component of the four texels that would be used in a bilinear filtering operation. |
| `GatherCmp` | `Texture2D`, `Texture2DArray`, `TextureCube`, `TextureCubeArray` | Gathers four texels and compares them against a reference value. |
| `GatherCmpRed` | `Texture2D`, `Texture2DArray`, `TextureCube`, `TextureCubeArray` | Gathers the red component of four texels and compares them against a reference value. |
| `GatherCmpGreen` | `Texture2D`, `Texture2DArray`, `TextureCube`, `TextureCubeArray` | Gathers the green component of four texels and compares them against a reference value. |
| `GatherCmpBlue` | `Texture2D`, `Texture2DArray`, `TextureCube`, `TextureCubeArray` | Gathers the blue component of four texels and compares them against a reference value. |
| `GatherCmpAlpha` | `Texture2D`, `Texture2DArray`, `TextureCube`, `TextureCubeArray` | Gathers the alpha component of four texels and compares them against a reference value. |
| `GetDimensions` | All `Texture*` and `RWTexture*` types | Retrieves the resource dimensions (width, height, and optionally mip levels or sample count). |
| `CalculateLevelOfDetail` | `Texture1D`, `Texture1DArray`, `Texture2D`, `Texture2DArray`, `Texture3D`, `TextureCube`, `TextureCubeArray` | Calculates the LOD that would be used for a given location, returning a clamped result. |
| `CalculateLevelOfDetailUnclamped` | `Texture1D`, `Texture1DArray`, `Texture2D`, `Texture2DArray`, `Texture3D`, `TextureCube`, `TextureCubeArray` | Calculates the LOD without clamping. |
| `GetSamplePosition` | `Texture2DMS`, `Texture2DMSArray` | Gets the position of the specified sample within a pixel. |
| `operator[]` | All `Texture*` and `RWTexture*` types | Accesses a texel at a specific location. |

### Codegen

#### Builtin Lowering

The HLSL builtins used in the record type implementation are lowered to
target-specific LLVM intrinsics in Clang codegen. The naming convention follows
[0014 - Consistent Naming for DX
Intrinsics](0014-consistent-naming-for-dx-intrinsics.md).

The LLVM intrinsics will be overloaded on the return type and the types of their
arguments (e.g., coordinates, offsets, derivatives). This avoids the need for
distinct intrinsic names for each texture dimension or type.

| HLSL Builtin                                      | LLVM Intrinsic                        |
| :------------------------------------------------ | :------------------------------------ |
| `__builtin_hlsl_resource_sample`                  | `llvm.<target>.resource.sample`       |
| `__builtin_hlsl_resource_sample_bias`             | `llvm.<target>.resource.samplebias`   |
| `__builtin_hlsl_resource_sample_grad`             | `llvm.<target>.resource.samplegrad`   |
| `__builtin_hlsl_resource_sample_level`            | `llvm.<target>.resource.samplelevel`  |
| `__builtin_hlsl_resource_sample_cmp`              | `llvm.<target>.resource.samplecmp`    |
| `__builtin_hlsl_resource_sample_cmp_level_zero`   | `llvm.<target>.resource.samplecmplevelzero` |
| `__builtin_hlsl_resource_load`                    | `llvm.<target>.resource.load.texture` |
| `__builtin_hlsl_resource_gather`                  | `llvm.<target>.resource.gather`       |
| `__builtin_hlsl_resource_gather_red`              | `llvm.<target>.resource.gather`       |
| `__builtin_hlsl_resource_gather_cmp`              | `llvm.<target>.resource.gathercmp`    |
| `__builtin_hlsl_resource_gather_cmp_red`          | `llvm.<target>.resource.gathercmp`    |
| `__builtin_hlsl_resource_calculate_lod`           | `llvm.<target>.resource.calculatelod` |
| `__builtin_hlsl_resource_calculate_lod_unclamped` | `llvm.<target>.resource.calculatelod` |
| `__builtin_hlsl_resource_get_sample_position`     | `llvm.<target>.resource.texturesamplepos` |

*   **Front-end**: Clang emits `llvm.dx.*` or `llvm.spv.*` intrinsics based on the
    target. The `<target>` in the table above is replaced by `dx` or `spv`
    respectively.
*   **Backend (DXIL)**: The `llvm.dx.resource.*` intrinsics are lowered to DXIL
    operations (e.g., `dx.op.sample`). Handle arguments are translated to
    `dx.Texture` and `dx.Sampler` types.

#### DXIL Translation

The following table shows the translation from the LLVM intrinsics to the DXIL
operations.

| LLVM Intrinsic | DXIL Op |
| :--- | :--- |
| `llvm.dx.resource.sample` | `dx.op.sample` (60) |
| `llvm.dx.resource.samplebias` | `dx.op.sampleBias` (61) |
| `llvm.dx.resource.samplegrad` | `dx.op.sampleGrad` (63) |
| `llvm.dx.resource.samplelevel` | `dx.op.sampleLevel` (62) |
| `llvm.dx.resource.samplecmp` | `dx.op.sampleCmp` (64) |
| `llvm.dx.resource.samplecmplevelzero` | `dx.op.sampleCmpLevelZero` (65) |
| `llvm.dx.resource.load.texture` | `dx.op.textureLoad` (66) |
| `llvm.dx.resource.gather` | `dx.op.textureGather` (73) |
| `llvm.dx.resource.gathercmp` | `dx.op.textureGatherCmp` (74) |
| `llvm.dx.resource.calculatelod` | `dx.op.calculateLOD` (81) |
| `llvm.dx.resource.texturesamplepos` | `dx.op.texture2DMSGetSamplePosition` (75) |

#### SPIR-V Translation

The following table shows the translation from the LLVM intrinsics to the SPIR-V
instructions.

| LLVM Intrinsic | SPIR-V Instruction |
| :--- | :--- |
| `llvm.spv.resource.sample` | `OpImageSampleImplicitLod` |
| `llvm.spv.resource.samplebias` | `OpImageSampleImplicitLod` with `Bias` operand |
| `llvm.spv.resource.samplegrad` | `OpImageSampleExplicitLod` with `Grad` operand |
| `llvm.spv.resource.samplelevel` | `OpImageSampleExplicitLod` with `Lod` operand |
| `llvm.spv.resource.samplecmp` | `OpImageSampleDrefImplicitLod` |
| `llvm.spv.resource.samplecmplevelzero` | `OpImageSampleDrefExplicitLod` with `Lod` 0 |
| `llvm.spv.resource.load.texture` | `OpImageFetch` |
| `llvm.spv.resource.gather` | `OpImageGather` |
| `llvm.spv.resource.gather_red` | `OpImageGather` with component 0 |
| `llvm.spv.resource.gather_green` | `OpImageGather` with component 1 |
| `llvm.spv.resource.gather_blue` | `OpImageGather` with component 2 |
| `llvm.spv.resource.gather_alpha` | `OpImageGather` with component 3 |
| `llvm.spv.resource.gathercmp` | `OpImageDrefGather` |
| `llvm.spv.resource.calculatelod` | `OpImageQueryLod` |
| `llvm.spv.resource.texturesamplepos` | Not supported |

### Sampler type in clang

The `SamplerState` and `SamplerComparisonState` types are classes containing a
single `__hlsl_resource_t` handle.

```cpp
struct SamplerState {
  __hlsl_resource_t [[hlsl::resource_class(Sampler)]] Handle;
};

struct SamplerComparisonState {
  __hlsl_resource_t [[hlsl::resource_class(Sampler)]] Handle;
};
```


### Offload test suite

We will create a specific test file for each member function group.

*   **Sample Methods**: Tests `Sample`, `SampleBias`, `SampleGrad`, `SampleLevel`.
*   **Comparison Sampling**: Tests `SampleCmp`, `SampleCmpLevelZero`.
*   **Load**: Tests `Load` and `operator[]`.
*   **Gather**: Tests `Gather` and its variants.
*   **Dimensions**: Tests `GetDimensions`.
*   **LOD Calculation**: Tests `CalculateLevelOfDetail`.
*   **Multisample**: Tests `GetSamplePosition` (DXIL only) and `Load` on MS
    textures.

#### Detailed Testing Example: SampleLevel

We will use `SampleLevel` on a `Texture2D` as a representative example of how
we verify these methods. The goal is to prove the compiler generates the
correct instruction with the correct arguments. We do not need to test every
possible combination of texture formats or dimensions, nor do we need to
verify the hardware's texture filtering hardware in depth.

**Test Strategy:**

1.  **Sampler Configuration:** Create two distinct samplers.
    *   `Samp1`: `MinFilter=Linear`, `MagFilter=Nearest`.
    *   `Samp2`: `MinFilter=Nearest`, `MagFilter=Linear` (or simply different
        address modes/border colors to distinguish).
    *   By using a specific sampler and getting the expected filtering result, we
        verify the correct sampler handle was passed.
2.  **Texture Setup:** Create a simple 2x2 texture with distinct colors for
    each quadrant:
    *   (0,0) Red, (1,0) Green, (0,1) Blue, (1,1) White.
3.  **LOD Verification:**
    *   Call `SampleLevel` with different LOD values using the same sampler and
        coordinates. Verify that the filtering results change as expected (e.g.,
        switching between magnification and minification).
4.  **Coordinate Verification:**
    *   Sample at different UV locations. Verify that the returned colors match
         the expected texels at those locations.
5.  **Non-Literal Parameter Verification:**
    *   Pass the LOD value from a runtime variable (e.g., loaded from a buffer).
        Verify that the compiler handles non-constant operands correctly.

**Example Test Case (Simplified):**

```yaml
#--- source.hlsl
[[vk::binding(0, 0)]] Texture2D<float4> Tex : register(t0);
[[vk::binding(1, 0)]] SamplerState Samp1 : register(s0); // Mag=Nearest, Min=Linear
[[vk::binding(2, 0)]] SamplerState Samp2 : register(s1); // Mag=Linear, Min=Nearest
[[vk::binding(3, 0)]] RWBuffer<float4> Out : register(u0);
[[vk::binding(4, 0)]] Buffer<float> In : register(t1); // Contains [-0.1]

[numthreads(1, 1, 1)]
void main() {
    float2 uv_tl = float2(0.25, 0.25); // Top-Left (Red)
    float2 uv_br = float2(0.75, 0.75); // Bottom-Right (White)

    // 1. Verify Sampler:
    // Same UV and LOD, different samplers.
    // LOD -0.1 -> Mag -> Samp1.Nearest -> Expects exact Red (1,0,0,1)
    Out[0] = Tex.SampleLevel(Samp1, uv_tl, -0.1);
    // LOD -0.1 -> Mag -> Samp2.Linear -> Expects blended value
    Out[1] = Tex.SampleLevel(Samp2, uv_tl, -0.1);

    // 2. Verify LOD:
    // Same sampler and UV, different LODs.
    // LOD -0.1 -> Mag -> Samp1.Nearest -> Expects exact Red (1,0,0,1)
    Out[2] = Tex.SampleLevel(Samp1, uv_tl, -0.1);
    // LOD 0.1 -> Min -> Samp1.Linear -> Expects blended value
    Out[3] = Tex.SampleLevel(Samp1, uv_tl, 0.1);

    // 3. Verify Coordinates:
    // Same sampler and LOD, different coordinates.
    // Sample top-left with Mag (Nearest) -> Expects Red (1,0,0,1)
    Out[4] = Tex.SampleLevel(Samp1, uv_tl, -0.1);
    // Sample bottom-right with Mag (Nearest) -> Expects White (1,1,1,1)
    Out[5] = Tex.SampleLevel(Samp1, uv_br, -0.1);

    // 4. Verify Non-Literal Parameters:
    // Load LOD from buffer. Value is -0.1.
    // LOD -0.1 -> Mag -> Samp1.Nearest -> Expects exact Red (1,0,0,1)
    float dynamic_lod = In[0];
    Out[6] = Tex.SampleLevel(Samp1, uv_tl, dynamic_lod);
}
```

This approach is sufficient because it isolates the compiler's responsibility:
mapping the HLSL method to the correct IR instruction with the user-provided
operands (sampler handle, coordinate vector, LOD float) preserved and ordered
correctly. Complex rendering behaviors are out of scope for compiler testing.
