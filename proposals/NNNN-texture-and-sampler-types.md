---
title: "[NNNN] - Texture and Sampler Types"
params:
  authors:
    - s-perron: Steven Perron
  status: Under Consideration
  sponsors:
---

## Introduction

This proposal describes the design for implementing Texture and Sampler types
in Clang for HLSL, including their frontend representation, LLVM IR
generation, and testing strategy within the offload-test-suite.

The implementation of the Texture and Sampler types will be modeled after
the implementation of `Buffer` and `RWBuffer`. We will define a resource
record type for each resource type. It will contain a handle with the
appropriate attributes. The member functions for the class will be
implemented as HLSL builtin functions. The builtin functions will be
translated to target-specific intrinsics during codegen.

## Motivation

Texture resources (`Texture2D`, `Texture3D`, etc.) and Samplers
(`SamplerState`, `SamplerComparisonState`) are fundamental to graphics
programming in HLSL.

## Proposed solution

The design follows the pattern established for `Buffer` and `RWBuffer`. Textures
and Samplers will be defined as record types in the HLSL External Sema Source. These records
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
* GetDimensions: See [0033 - Resource GetDimensions](0033-resources-get-dimensions.md).

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

We will use mipmapped textures to verify that the compiler and drivers correctly
handle multiple levels of detail. This allows us to verify:
*   `CalculateLevelOfDetail` and `CalculateLevelOfDetailUnclamped` correctly 
    report the level of detail across multiple levels.
*   `SampleGrad` correctly selects the expected mip level based on provided
    derivatives.
*   `mips.operator[][]` correctly accesses data from non-zero mip levels.
*   `GetDimensions` correctly reports the total number of mip levels.

## Detailed design

### Texture type in clang

#### The resource record type

Texture resources are represented in Clang using a record type defined in the
HLSL External Sema Source. This record exposes the interface that the developer uses. Its
implementation contains a single member of type `__hlsl_resource_t`, annotated
with appropriate attributes to denote the specific resource kind (e.g.,
`Texture2D`, `TextureCube`) and element type. See [0015 - Mapping Resource
Attributes to DXIL and SPIR-V](0015-resource-attributes-in-dxil-and-spirv.md) for detail 
on which attributes will apply to which texture types.



The member functions are implemented as calls to HLSL builtin functions. These
builtins take the resource handle as the first parameter and forward the
remaining arguments.

When a member function requires a sampler (e.g., `Sample`), the `SamplerState`
object is passed to the member function. The implementation extracts the handle
from the `SamplerState` record and passes it to the underlying builtin.

For example, `Texture2D<T>` would look effectively like:

```cpp
template <typename T>
class Texture2D {
  __hlsl_resource_t [[hlsl::resource_class(SRV)]]
                    [[hlsl::dimension(2D)]]
                    [[hlsl::contained_type(T)]] Handle;

public:
  // ... Standard constructors ...
  // See 0025 - Resource Initialization and Constructors

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
    return __builtin_hlsl_resource_load(Handle, location.xy, location.z);
  }
  // ... other Load overloads ...

  // Implemented the same way as `Buffer`.
  const T& operator[](int2 pos) {
    return *__builtin_hlsl_resource_getpointer(Handle, pos);
  }

  // mips operator
  struct MipsCurry {
    __hlsl_resource_t Handle;
    uint MipLevel;
    T operator[](int2 Loc) {
      return __builtin_hlsl_resource_load(Handle, Loc, MipLevel);
    }
  };

  struct Mips {
    __hlsl_resource_t Handle;
    MipsCurry operator[](uint MipLevel) {
      return {Handle, MipLevel};
    }
  } mips;

  // Gather
  vec<GetElementType(T), 4> Gather(SamplerState s, float2 location) {
    return __builtin_hlsl_resource_gather(Handle, s.Handle, 
                                          location);
  }
  // ... other Gather overloads ...

  // Variants for Green, Blue, Alpha
  vec<GetElementType(T), 4> GatherRed(SamplerState s, float2 location) {
      return __builtin_hlsl_resource_gather_red(Handle, s.Handle, 
                                                location);
  }
  // ...

   vec<GetElementType(T), 4> GatherCmp(SamplerComparisonState s, float2 location, 
                             float compare_value) {
    return __builtin_hlsl_resource_gather_cmp(Handle, s.Handle, 
                                              location, compare_value);
  }
  // ... other GatherCmp overloads ...

  vec<GetElementType(T), 4> GatherCmpRed(SamplerComparisonState s, float2 location, 
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

The following sections describe the member functions and the texture types that support
them.

##### `CalculateLevelOfDetail`

* **Description**: Calculates the LOD that would be used for a given location,
  returning a clamped result.
* **Implementation**: Implemented using the `__builtin_hlsl_resource_calculate_lod` builtin.
* **Supported Types**:
  * [Texture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-calculate-lod)
  * [Texture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-calculate-lod)
  * [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-calculate-lod)
  * [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-calculate-lod)
  * [Texture3D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-calculate-lod)
  * [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-calculate-lod)
  * [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-calculate-lod)

##### `CalculateLevelOfDetailUnclamped`

* **Description**: Calculates the LOD without clamping.
* **Implementation**: Implemented using the `__builtin_hlsl_resource_calculate_lod_unclamped` builtin.
* **Supported Types**:
  * [Texture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-calculate-lod-unclamped)
  * [Texture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-calculate-lod-unclamped)
  * [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-calculate-lod-unclamped)
  * [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-calculate-lod-unclamped)
  * [Texture3D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-calculate-lod-unclamped)
  * [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-calculate-lod-unclamped)
  * [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-calculate-lod-unclamped)

##### `Gather`

* **Description**: Returns the four texels that would be used in a bilinear
  filtering operation.
* **Implementation**: Implemented using the `__builtin_hlsl_resource_gather` builtin.
* **Supported Types**:
  * [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2d-gather)
  * [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2darray-gather)
  * [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecube-gather)
  * [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecubearray-gather)

##### `GatherAlpha`

* **Description**: Returns the alpha component of the four texels that would be
  used in a bilinear filtering operation.
* **Implementation**: Implemented using the `__builtin_hlsl_resource_gather_alpha` builtin.
* **Supported Types**:
  * [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2d-gatheralpha)
  * [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2darray-gatheralpha)
  * [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecube-gatheralpha)
  * [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecubearray-gatheralpha)

##### `GatherBlue`

* **Description**: Returns the blue component of the four texels that would be
  used in a bilinear filtering operation.
* **Implementation**: Implemented using the `__builtin_hlsl_resource_gather_blue` builtin.
* **Supported Types**:
  * [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2d-gatherblue)
  * [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2darray-gatherblue)
  * [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecube-gatherblue)
  * [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecubearray-gatherblue)

##### `GatherCmp`

* **Description**: Gathers four texels and compares them against a reference value.
* **Implementation**: Implemented using the `__builtin_hlsl_resource_gather_cmp` builtin.
* **Supported Types**:
  * [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2d-gathercmp)
  * [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2darray-gathercmp)
  * [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecube-gathercmp)
  * [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecubearray-gathercmp)

##### `GatherCmpAlpha`

* **Description**: Gathers the alpha component of four texels and compares them
  against a reference value. This is not supported in SPIR-V and will error
  during semantic analysis.
* **Implementation**: Implemented using the `__builtin_hlsl_resource_gather_cmp_alpha` builtin.
* **Supported Types**:
  * [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2d-gathercmpalpha)
  * [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2darray-gathercmpalpha)
  * [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecube-gathercmpalpha)
  * [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecubearray-gathercmpalpha)

##### `GatherCmpBlue`

* **Description**: Gathers the blue component of four texels and compares them
  against a reference value. This is not supported in SPIR-V and will error
  during semantic analysis.
* **Implementation**: Implemented using the `__builtin_hlsl_resource_gather_cmp_blue` builtin.
* **Supported Types**:
  * [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2d-gathercmpblue)
  * [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2darray-gathercmpblue)
  * [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecube-gathercmpblue)
  * [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecubearray-gathercmpblue)

##### `GatherCmpGreen`

* **Description**: Gathers the green component of four texels and compares them
  against a reference value. This is not supported in SPIR-V and will error
  during semantic analysis.
* **Implementation**: Implemented using the `__builtin_hlsl_resource_gather_cmp_green` builtin.
* **Supported Types**:
  * [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2d-gathercmpgreen)
  * [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2darray-gathercmpgreen)
  * [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecube-gathercmpgreen)
  * [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecubearray-gathercmpgreen)

##### `GatherCmpRed`

* **Description**: Gathers the red component of four texels and compares them
  against a reference value.
* **Implementation**: Implemented using the `__builtin_hlsl_resource_gather_cmp_red` builtin.
* **Supported Types**:
  * [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2d-gathercmpred)
  * [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2darray-gathercmpred)
  * [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecube-gathercmpred)
  * [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecubearray-gathercmpred)

##### `GatherGreen`

* **Description**: Returns the green component of the four texels that would be
  used in a bilinear filtering operation.
* **Implementation**: Implemented using the `__builtin_hlsl_resource_gather_green` builtin.
* **Supported Types**:
  * [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2d-gathergreen)
  * [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2darray-gathergreen)
  * [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecube-gathergreen)
  * [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecubearray-gathergreen)

##### `GatherRed`

* **Description**: Returns the red component of the four texels that would be
  used in a bilinear filtering operation.
* **Implementation**: Implemented using the `__builtin_hlsl_resource_gather_red` builtin.
* **Supported Types**:
  * [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2d-gatherred)
  * [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2darray-gatherred)
  * [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecube-gatherred)
  * [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecubearray-gatherred)

##### `GetDimensions`

* **Description**: Retrieves the resource dimensions (width, height, and
  optionally mip levels or sample count).
* **Implementation**: Implemented using the builtins defined in [0033 - Resource GetDimensions](0033-resources-get-dimensions.md).
* **Supported Types**:
  * [Texture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-getdimensions)
  * [Texture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-getdimensions)
  * [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-getdimensions)
  * [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-getdimensions)
  * [Texture3D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-getdimensions)
  * [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-getdimensions)
  * [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-getdimensions)
  * [Texture2DMS](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-getdimensions)
  * [Texture2DMSArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-getdimensions)
  * [RWTexture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture1d-getdimensions)
  * [RWTexture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture1darray-getdimensions)
  * [RWTexture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture2d-getdimensions)
  * [RWTexture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture2darray-getdimensions)
  * [RWTexture3D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture3d-getdimensions)

##### `GetSamplePosition`

* **Description**: Gets the position of the specified sample within a pixel.
* **Implementation**: Implemented using the `__builtin_hlsl_resource_get_sample_position` builtin.
* **Supported Types**:
  * [Texture2DMS](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-get-sample-position)
  * [Texture2DMSArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-get-sample-position)

##### `Load`

* **Description**: Reads texture data directly (texel fetch) without a sampler.
* **Implementation**: Implemented using the `__builtin_hlsl_resource_load` builtin.
* **Supported Types**:
  * [Texture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture1d-load)
  * [Texture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture1darray-load)
  * [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2d-load)
  * [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2darray-load)
  * [Texture3D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture3d-load)
  * [Texture2DMS](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2dms-load)
  * [Texture2DMSArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2dmsarray-load)
  * [RWTexture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture1d-load)
  * [RWTexture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture1darray-load)
  * [RWTexture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture2d-load)
  * [RWTexture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture2darray-load)
  * [RWTexture3D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture3d-load)

##### `mips.Operator[][]`

* **Description**: Accesses a texel at a specific mip level and location.
* **Implementation**: Implemented using the `__builtin_hlsl_resource_load` builtin.
* **Supported Types**:
  * [Texture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-texture1d-mipsoperatorindex)
  * [Texture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-texture1darray-mipsoperatorindex)
  * [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-texture2d-mipsoperatorindex)
  * [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-texture2darray-mipsoperatorindex)
  * [Texture3D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-texture3d-mipsoperatorindex)

##### `sample.operator[][]`

* **Description**: Accesses a single sample.
* **Implementation**: TODO
* **Supported Types**:
  * [Texture2DMS](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-texture2dms-sampleoperatorindex)
  * [Texture2DMSArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-texture2dmsarray-sampleoperatorindex)

##### `Sample`

* **Description**: Samples the texture using a sampler.
* **Implementation**: Implemented using the `__builtin_hlsl_resource_sample` builtin.
* **Supported Types**:
  * [Texture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture1d-sample)
  * [Texture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture1darray-sample)
  * [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2d-sample)
  * [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2darray-sample)
  * [Texture3D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture3d-sample)
  * [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecube-sample)
  * [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecubearray-sample)

##### `SampleBias`

* **Description**: Samples the texture after applying a bias value to the mip level.
* **Implementation**: Implemented using the `__builtin_hlsl_resource_sample_bias` builtin.
* **Supported Types**:
  * [Texture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture1d-samplebias)
  * [Texture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture1darray-samplebias)
  * [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2d-samplebias)
  * [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2darray-samplebias)
  * [Texture3D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture3d-samplebias)
  * [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecube-samplebias)
  * [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecubearray-samplebias)

##### `SampleCmp`

* **Description**: Samples the texture and compares the result against a
  comparison value.
* **Implementation**: Implemented using the `__builtin_hlsl_resource_sample_cmp` builtin.
* **Supported Types**:
  * [Texture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture1d-samplecmp)
  * [Texture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture1darray-samplecmp)
  * [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2d-samplecmp)
  * [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2darray-samplecmp)
  * [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecube-samplecmp)
  * [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecubearray-samplecmp)

##### `SampleCmpLevelZero`

* **Description**: Samples the texture (mip level 0 only) and compares the
  result against a comparison value.
* **Implementation**: Implemented using the `__builtin_hlsl_resource_sample_cmp_level_zero` builtin.
* **Supported Types**:
  * [Texture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture1d-samplecmplevelzero)
  * [Texture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture1darray-samplecmplevelzero)
  * [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2d-samplecmplevelzero)
  * [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2darray-samplecmplevelzero)
  * [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecube-samplecmplevelzero)
  * [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecubearray-samplecmplevelzero)

##### `SampleGrad`

* **Description**: Samples the texture using gradients to influence the sample
  location calculation.
* **Implementation**: Implemented using the `__builtin_hlsl_resource_sample_grad` builtin.
* **Supported Types**:
  * [Texture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture1d-samplegrad)
  * [Texture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture1darray-samplegrad)
  * [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2d-samplegrad)
  * [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2darray-samplegrad)
  * [Texture3D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture3d-samplegrad)
  * [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecube-samplegrad)
  * [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecubearray-samplegrad)

##### `SampleLevel`

* **Description**: Samples the texture on the specified mip level.
* **Implementation**: Implemented using the `__builtin_hlsl_resource_sample_level` builtin.
* **Supported Types**:
  * [Texture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture1d-samplelevel)
  * [Texture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture1darray-samplelevel)
  * [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2d-samplelevel)
  * [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2darray-samplelevel)
  * [Texture3D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture3d-samplelevel)
  * [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecube-samplelevel)
  * [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecubearray-samplelevel)

##### `operator[]`

* **Description**: Accesses a texel at a specific location.
* **Implementation**: Implemented by dereferencing the result of the `__builtin_hlsl_resource_getpointer` builtin.
* **Supported Types**:
  * [Texture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-texture1d-operatorindex)
  * [Texture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-texture1darray-operatorindex)
  * [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-texture2d-operatorindex)
  * [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-texture2darray-operatorindex)
  * [Texture3D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-texture3d-operatorindex)
  * [Texture2DMS](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-texture2dms-operator1)
  * [RWTexture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture1d-operatorindex)
  * [RWTexture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture1darray-operatorindex)
  * [RWTexture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture2d-operatorindex)
  * [RWTexture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture2darray-operatorindex)
  * [RWTexture3D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture3d-operatorindex)

### HLSL Builtin Interface

This section details the parameters for the clang builtins. Optional parameters
are indicated. If an optional parameter is not provided, a default value of 0 is
used.

*   `T __builtin_hlsl_resource_sample(Handle, Sampler, Coord, int2 Offset = 0)`
*   `T __builtin_hlsl_resource_sample_bias(Handle, Sampler, Coord, float Bias, int2 Offset = 0)`
*   `T __builtin_hlsl_resource_sample_grad(Handle, Sampler, Coord, float2 DDX, float2 DDY, int2 Offset = 0)`
*   `T __builtin_hlsl_resource_sample_level(Handle, Sampler, Coord, float LOD, int2 Offset = 0)`
*   `float __builtin_hlsl_resource_sample_cmp(Handle, Sampler, Coord, float CompareValue, int2 Offset = 0)`
*   `float __builtin_hlsl_resource_sample_cmp_level_zero(Handle, Sampler, Coord, float CompareValue, int2 Offset = 0)`
*   `T __builtin_hlsl_resource_load(Handle, Coord, int MipLevelOrSampleIndex = 0, int2 Offset = 0)`
*   `float4 __builtin_hlsl_resource_gather(Handle, Sampler, Coord, int2 Offset = 0)`
*   `float4 __builtin_hlsl_resource_gather_[red|green|blue|alpha](Handle, Sampler, Coord, int2 Offset = 0)`
*   `float4 __builtin_hlsl_resource_gather_cmp(Handle, Sampler, Coord, float CompareValue, int2 Offset = 0)`
*   `float4 __builtin_hlsl_resource_gather_cmp_[red|green|blue|alpha](Handle, Sampler, Coord, float CompareValue, int2 Offset = 0)`
*   `float __builtin_hlsl_resource_calculate_lod(Handle, Sampler, Coord)`
*   `float __builtin_hlsl_resource_calculate_lod_unclamped(Handle, Sampler, Coord)`
*   `float2 __builtin_hlsl_resource_get_sample_position(Handle, uint SampleIndex)`
*   For `GetDimensions` intrinsics, see [0033 - Resource GetDimensions](0033-resources-get-dimensions.md).

### Codegen

#### Builtin Lowering

The HLSL builtins used in the record type implementation are lowered to
target-specific LLVM intrinsics in Clang codegen. The naming convention follows
[0014 - Consistent Naming for DX
Intrinsics](0014-consistent-naming-for-dx-intrinsics.md).

The `__builtin_hlsl_resource_load` builtin will support default values for
optional operands. Specifically, `SampleIndex` will default to 0 for
non-multisampled textures, and `Offset` will default to 0 if not provided.
This allows a single builtin to handle the various `Load` overloads.

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
| `llvm.spv.resource.texturesamplepos` | Emulated |

The intrinsic `llvm.spv.resource.texturesamplepos` is not directly supported in
Vulkan, but it is emulated by using a lookup table of standard sample positions.
The implementation works as follows:

1.  **Query Sample Count**: The sample count of the texture is queried using
    `OpImageQuerySamples`.
2.  **Select Position Array**: Based on the sample count, a specific constant
    array of sample positions is selected.
    *   **Count 1**: Returns `(0, 0)`
    *   **Count 2**:
        *   0: `(0.25, 0.25)`
        *   1: `(-0.25, -0.25)`
    *   **Count 4**:
        *   0: `(-0.125, -0.375)`
        *   1: `(0.375, -0.125)`
        *   2: `(-0.375, 0.125)`
        *   3: `(0.125, 0.375)`
    *   **Count 8**:
        *   0: `(0.0625, -0.1875)`
        *   1: `(-0.0625, 0.1875)`
        *   2: `(0.3125, 0.0625)`
        *   3: `(-0.1875, -0.3125)`
        *   4: `(-0.3125, 0.3125)`
        *   5: `(-0.4375, -0.0625)`
        *   6: `(0.1875, 0.4375)`
        *   7: `(0.4375, -0.4375)`
    *   **Count 16**:
        *   0: `(0.0625, 0.0625)`
        *   1: `(-0.0625, -0.1875)`
        *   2: `(-0.1875, 0.125)`
        *   3: `(0.25, -0.0625)`
        *   4: `(-0.3125, -0.125)`
        *   5: `(0.125, 0.3125)`
        *   6: `(0.3125, 0.1875)`
        *   7: `(0.1875, -0.3125)`
        *   8: `(-0.125, 0.375)`
        *   9: `(0, -0.4375)`
        *   10: `(-0.25, -0.375)`
        *   11: `(-0.375, 0.25)`
        *   12: `(-0.5, 0)`
        *   13: `(0.4375, -0.25)`
        *   14: `(0.375, 0.4375)`
        *   15: `(-0.4375, -0.5)`
3.  **Lookup**: The `SampleIndex` is used to index into the selected array.
4.  **Fallback**: If the sample count is not supported or no array is found, the
    function returns `(0, 0)`.

This matches the current DXC implementation.

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
