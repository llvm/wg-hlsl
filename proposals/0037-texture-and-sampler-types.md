---
title: "[0037] - Texture and Sampler Types"
params:
  authors:
    - s-perron: Steven Perron
    - icohedron: Deric Cheung
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

Texture resources (`Texture2D`, `Texture3D`, etc.) and Samplers (`SamplerState`,
`SamplerComparisonState`) are fundamental to graphics programming in HLSL.

## Proposed solution

The design follows the pattern established for `Buffer` and `RWBuffer`. Textures
and Samplers will be defined as record types in the HLSL External Sema Source.
These records will wrap an internal `__hlsl_resource_t` handle. Member functions
will be implemented as wrappers that call clang builtins, passing the underlying
resource handles.

This design will cover the implementation of:

- `Texture1D`
- `Texture2D`
- `Texture3D`
- `TextureCube`
- `Texture1DArray`
- `Texture2DArray`
- `TextureCubeArray`
- `Texture2DMS`
- `Texture2DMSArray`
- `RWTexture1D`
- `RWTexture2D`
- `RWTexture3D`
- `RWTexture1DArray`
- `RWTexture2DArray`
- `SamplerState`
- `SamplerComparisonState`

Many elements of the design will be the same as other resources or have already
been designed:

- Initialization and constructors: See
  [0025 - Resource Initialization and Constructors](0025-resource-initialization-and-constructors.md).
- Binding: See
  [0024 - Implicit Resource Binding](0024-implicit-resource-binding.md) and
  [0030 - Vulkan Resource Binding](0030-vulkan-resource-binding.md).
- Resource attributes: See
  [0015 - Mapping Resource Attributes to DXIL and SPIR-V](0015-resource-attributes-in-dxil-and-spirv.md).
- Target types: See
  [0018 - HLSL resources in SPIR-V](0018-spirv-resource-representation.md) and
  [0015 - Mapping Resource Attributes to DXIL and SPIR-V](0015-resource-attributes-in-dxil-and-spirv.md).
- GetDimensions: See
  [0033 - Resource GetDimensions](0033-resources-get-dimensions.md).
- Default Template Arguments and Shorthand: See
  [0042 - Texture Default Templates](0042-texture-default-templates.md).

The detailed design in this proposal will fill in the details of the
`HLSLAttributedResourceType` for these types. It should follow the design in
[0006 - Resource Representations in Clang and LLVM](0006-resource-representations.md).

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

- `CalculateLevelOfDetail` and `CalculateLevelOfDetailUnclamped` correctly
  report the level of detail across multiple levels.
- `SampleGrad` correctly selects the expected mip level based on provided
  derivatives.
- `mips.operator[][]` correctly accesses data from non-zero mip levels.
- `GetDimensions` correctly reports the total number of mip levels.

## Detailed design

### Texture type in clang

#### The resource record type

Texture resources are represented in Clang using a record type defined in the
HLSL External Sema Source. This record exposes the interface that the developer
uses. Its implementation contains a single member of type `__hlsl_resource_t`,
annotated with appropriate attributes to denote the specific resource kind
(e.g., `Texture2D`, `TextureCube`) and element type. See
[0015 - Mapping Resource Attributes to DXIL and SPIR-V](0015-resource-attributes-in-dxil-and-spirv.md)
for detail on which attributes will apply to which texture types.

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
    return __builtin_hlsl_resource_load_level(Handle, location);
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
      return __builtin_hlsl_resource_load_level(Handle, uint3(Loc, MipLevel));
    }
  };

  struct Mips {
    __hlsl_resource_t Handle;
    MipsCurry operator[](uint MipLevel) {
      return {Handle, MipLevel};
    }
  } mips;

  // Gather
  vec<GetElementType(T), 4> Gather(SamplerState s, float2 location, int2 Offset = 0) {
    return __builtin_hlsl_resource_gather(Handle, s.Handle, location, 0, Offset);
  }
  // ... other Gather overloads ...

  // Variants for Green, Blue, Alpha
  vec<GetElementType(T), 4> GatherRed(SamplerState s, float2 location, int2 Offset = 0) {
      return __builtin_hlsl_resource_gather(Handle, s.Handle, location, 0, Offset);
  }
  vec<GetElementType(T), 4> GatherGreen(SamplerState s, float2 location, int2 Offset = 0) {
      return __builtin_hlsl_resource_gather(Handle, s.Handle, location, 1, Offset);
  }
  // ... Blue (2), Alpha (3)

   vec<GetElementType(T), 4> GatherCmp(SamplerComparisonState s, float2 location,
                             float compare_value, int2 Offset = 0) {
    return __builtin_hlsl_resource_gather_cmp(Handle, s.Handle, location, compare_value, 0, Offset);
  }
  // ... other GatherCmp overloads ...

  vec<GetElementType(T), 4> GatherCmpRed(SamplerComparisonState s, float2 location,
                                float compare_value, int2 Offset = 0) {
      return __builtin_hlsl_resource_gather_cmp(Handle, s.Handle, location, compare_value, 0, Offset);
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

#### Vector Specialization and Gather Return Types

The `Gather` methods (and variants like `GatherRed`, `GatherCmp`, etc.) are
unique because their return type is always a 4-element vector of the texture's
underlying scalar element type, regardless of whether the texture's template
parameter `T` is a scalar or a vector.

To correctly implement the return type for these methods, we add a partial
specialization of the texture type for vector types:

```cpp
template <typename ElementType, unsigned int Size>
class Texture2D<vector<ElementType, Size>> {
  // Same as the primary template, but Gather methods return vec<ElementType, 4>
};
```

During the design phase, we evaluated alternatives for defining the `Gather`
return type, but they were not viable:

1. **Using `auto` return type:** We considered using `auto` for the return type
   of the `Gather` functions and letting the compiler deduce it. However, `auto`
   return type deduction is not a feature currently supported in HLSL, and we
   did not want to partially enable it just for these methods.
2. **Standalone class with a typedef and partial specialization:** We attempted
   to create a standalone helper class to deduce the return type via a
   `typedef`, which the `Texture2D` class could then use. However, this caused
   Clang to assert when the template was instantiated in compiler-generated code
   (due to an `Invalid SourceLocation`). Fixing this would require an unknown
   and potentially pervasive change to how Clang handles source locations in
   implicitly generated template code.

Therefore, the partial specialization of the resource record type is the chosen
approach to ensure the correct return type for `Gather` operations.

#### Member functions

The following sections describe the member functions and the texture types that
support them.

##### `CalculateLevelOfDetail`

- **Description**: Calculates the LOD that would be used for a given location,
  returning a clamped result.
- **Implementation**: Implemented using the
  `__builtin_hlsl_resource_calculate_lod` builtin.
- **Supported Types**:
  - [Texture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-calculate-lod)
  - [Texture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-calculate-lod)
  - [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-calculate-lod)
  - [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-calculate-lod)
  - [Texture3D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-calculate-lod)
  - [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-calculate-lod)
  - [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-calculate-lod)

##### `CalculateLevelOfDetailUnclamped`

- **Description**: Calculates the LOD without clamping.
- **Implementation**: Implemented using the
  `__builtin_hlsl_resource_calculate_lod_unclamped` builtin.
- **Supported Types**:
  - [Texture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-calculate-lod-unclamped)
  - [Texture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-calculate-lod-unclamped)
  - [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-calculate-lod-unclamped)
  - [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-calculate-lod-unclamped)
  - [Texture3D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-calculate-lod-unclamped)
  - [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-calculate-lod-unclamped)
  - [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-calculate-lod-unclamped)

##### `Gather`, `GatherAlpha`, `GatherBlue`, `GatherRed`, `GatherGreen`

- **Description**: Returns the appropriate componenets of the four texels that
  would be used in a bilinear filtering operation.
- **Implementation**: Implemented using the `__builtin_hlsl_resource_gather`
  builtin.
- **Supported Types**:
  - [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2d-gather)
  - [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2darray-gather)
  - [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecube-gather)
  - [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecubearray-gather)

##### `GatherCmp`, `GatherCmpAlpha`, `GatherCmpBlue`, `GatherCmpRed`, `GatherCmpGreen`

- **Description**: Gathers four texels and compares appropriate components
  against a reference value.
- **Implementation**: Implemented using the `__builtin_hlsl_resource_gather_cmp`
  builtin.
- **Supported Types**:
  - [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2d-gathercmp)
  - [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2darray-gathercmp)
  - [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecube-gathercmp)
  - [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecubearray-gathercmp)

##### `GetDimensions`

- **Description**: Retrieves the resource dimensions (width, height, and
  optionally mip levels or sample count).
- **Implementation**: Implemented using the builtins defined in
  [0033 - Resource GetDimensions](0033-resources-get-dimensions.md).
- **Supported Types**:
  - [Texture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-getdimensions)
  - [Texture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-getdimensions)
  - [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-getdimensions)
  - [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-getdimensions)
  - [Texture3D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-getdimensions)
  - [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-getdimensions)
  - [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-getdimensions)
  - [Texture2DMS](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-getdimensions)
  - [Texture2DMSArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-getdimensions)
  - [RWTexture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture1d-getdimensions)
  - [RWTexture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture1darray-getdimensions)
  - [RWTexture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture2d-getdimensions)
  - [RWTexture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture2darray-getdimensions)
  - [RWTexture3D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture3d-getdimensions)

##### `GetSamplePosition`

- **Description**: Gets the position of the specified sample within a pixel.
- **Implementation**: Implemented using the
  `__builtin_hlsl_resource_get_sample_position` builtin.
- **Supported Types**:
  - [Texture2DMS](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-get-sample-position)
  - [Texture2DMSArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-to-get-sample-position)

##### `Load`

- **Description**: Reads texture data directly (texel fetch) without a sampler.
- **Implementation**: Implemented using the `__builtin_hlsl_resource_load_level`
  builtin.
- **Supported Types**:
  - [Texture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture1d-load)
  - [Texture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture1darray-load)
  - [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2d-load)
  - [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2darray-load)
  - [Texture3D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture3d-load)
  - [Texture2DMS](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2dms-load)
  - [Texture2DMSArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2dmsarray-load)
  - [RWTexture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture1d-load)
  - [RWTexture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture1darray-load)
  - [RWTexture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture2d-load)
  - [RWTexture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture2darray-load)
  - [RWTexture3D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture3d-load)

##### `mips.Operator[][]`

- **Description**: Accesses a texel at a specific mip level and location.
- **Implementation**: Implemented using the `__builtin_hlsl_resource_load_level`
  builtin.
- **Supported Types**:
  - [Texture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-texture1d-mipsoperatorindex)
  - [Texture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-texture1darray-mipsoperatorindex)
  - [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-texture2d-mipsoperatorindex)
  - [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-texture2darray-mipsoperatorindex)
  - [Texture3D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-texture3d-mipsoperatorindex)

##### `sample.operator[][]`

- **Description**: Accesses a single sample at a given position in a
  multisampled texture.
- **Implementation**: Implemented using the `__builtin_hlsl_resource_load_ms`
  builtin.
- **Supported Types**:
  - [Texture2DMS](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-texture2dms-sampleoperatorindex)
  - [Texture2DMSArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-texture2dmsarray-sampleoperatorindex)

##### `Sample`

- **Description**: Samples the texture using a sampler.
- **Implementation**: Implemented using the `__builtin_hlsl_resource_sample`
  builtin.
- **Supported Types**:
  - [Texture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture1d-sample)
  - [Texture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture1darray-sample)
  - [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2d-sample)
  - [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2darray-sample)
  - [Texture3D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture3d-sample)
  - [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecube-sample)
  - [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecubearray-sample)

##### `SampleBias`

- **Description**: Samples the texture after applying a bias value to the mip
  level.
- **Implementation**: Implemented using the
  `__builtin_hlsl_resource_sample_bias` builtin.
- **Supported Types**:
  - [Texture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture1d-samplebias)
  - [Texture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture1darray-samplebias)
  - [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2d-samplebias)
  - [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2darray-samplebias)
  - [Texture3D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture3d-samplebias)
  - [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecube-samplebias)
  - [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecubearray-samplebias)

##### `SampleCmp`

- **Description**: Samples the texture and compares the result against a
  comparison value.
- **Implementation**: Implemented using the `__builtin_hlsl_resource_sample_cmp`
  builtin.
- **Supported Types**:
  - [Texture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture1d-samplecmp)
  - [Texture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture1darray-samplecmp)
  - [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2d-samplecmp)
  - [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2darray-samplecmp)
  - [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecube-samplecmp)
  - [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecubearray-samplecmp)

##### `SampleCmpLevelZero`

- **Description**: Samples the texture (mip level 0 only) and compares the
  result against a comparison value.
- **Implementation**: Implemented using the
  `__builtin_hlsl_resource_sample_cmp_level_zero` builtin.
- **Supported Types**:
  - [Texture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture1d-samplecmplevelzero)
  - [Texture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture1darray-samplecmplevelzero)
  - [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2d-samplecmplevelzero)
  - [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2darray-samplecmplevelzero)
  - [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecube-samplecmplevelzero)
  - [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecubearray-samplecmplevelzero)

##### `SampleGrad`

- **Description**: Samples the texture using gradients to influence the sample
  location calculation.
- **Implementation**: Implemented using the
  `__builtin_hlsl_resource_sample_grad` builtin.
- **Supported Types**:
  - [Texture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture1d-samplegrad)
  - [Texture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture1darray-samplegrad)
  - [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2d-samplegrad)
  - [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2darray-samplegrad)
  - [Texture3D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture3d-samplegrad)
  - [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecube-samplegrad)
  - [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecubearray-samplegrad)

##### `SampleLevel`

- **Description**: Samples the texture on the specified mip level.
- **Implementation**: Implemented using the
  `__builtin_hlsl_resource_sample_level` builtin.
- **Supported Types**:
  - [Texture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture1d-samplelevel)
  - [Texture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture1darray-samplelevel)
  - [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2d-samplelevel)
  - [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture2darray-samplelevel)
  - [Texture3D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texture3d-samplelevel)
  - [TextureCube](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecube-samplelevel)
  - [TextureCubeArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/texturecubearray-samplelevel)

##### `operator[]`

- **Description**: Accesses a texel at a specific location.
- **Implementation**: Implemented by dereferencing the result of the
  `__builtin_hlsl_resource_getpointer` builtin.
- **Supported Types**:
  - [Texture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-texture1d-operatorindex)
  - [Texture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-texture1darray-operatorindex)
  - [Texture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-texture2d-operatorindex)
  - [Texture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-texture2darray-operatorindex)
  - [Texture3D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-texture3d-operatorindex)
  - [Texture2DMS](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-texture2dms-operator1)
  - [RWTexture1D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture1d-operatorindex)
  - [RWTexture1DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture1darray-operatorindex)
  - [RWTexture2D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture2d-operatorindex)
  - [RWTexture2DArray](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture2darray-operatorindex)
  - [RWTexture3D](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sm5-object-rwtexture3d-operatorindex)

#### Sema Diagnostics

The builtins underlying each member function perform semantic validation of
their arguments. The following sections describe the diagnostics that apply
to texture and sampler types.

##### Template Parameter Validation

Texture template parameters are constrained using the same
[`__is_typed_resource_element_compatible` concept][typed-resource-concept]
as `Buffer` and `RWBuffer`. Valid element types are scalars and vectors of
numeric types (excluding `bool` and enums) that fit in four 32-bit quantities
(16 bytes). Structs, arrays, matrices, and resource types are rejected.
`double` and `double2` satisfy this constraint (8 and 16 bytes respectively), so
additional validation at the point of use is needed for operations that do not
support 64-bit element types.

[typed-resource-concept]: 0011-resource-element-type-validation.md

##### Sampling Element Type Validation

The `Sample`, `SampleBias`, `SampleGrad`, `SampleLevel`, `SampleCmp`,
`SampleCmpLevelZero`, and `Gather` methods validate that the resource's
contained element type is compatible with the operation:

- `double` element types are always rejected for sample and gather methods.
- Integer element types (`int`, `uint`, `int16_t`, `uint16_t`) are rejected for
  `Sample`, `SampleBias`, `SampleGrad`, and `SampleLevel` when the target is
  below SM 6.7 (see [HLSL Advanced Texture Operations - Integer Sampling][integer-sampling]).
- `SampleCmp`, `SampleCmpLevelZero`, and `SampleCmpLevel` require the element
  type to be floating-point, regardless of shader model version.

These restrictions match [DXC's validation][dxc-validation] behavior.

[integer-sampling]: https://microsoft.github.io/DirectX-Specs/d3d/HLSL_SM_6_7_Advanced_Texture_Ops.html#integer-sampling
[dxc-validation]: https://github.com/microsoft/DirectXShaderCompiler/blob/7284bb1809613fb12d61cc0426afa4057afb0265/tools/clang/lib/Sema/SemaHLSL.cpp#L6908-L6948

##### Coordinate and Argument Validation

Coordinate vectors must match the resource's dimensionality. The expected
dimensions per type are:

| Texture Type       | Sample Coord | Load Coord            | `operator[]` Index | Offset |
|--------------------|--------------|-----------------------|--------------------|--------|
| `Texture1D`        | `float`      | `int2` (x + mip)      | `uint`             | `int`  |
| `Texture1DArray`   | `float2`     | `int3`                | `uint2`            | `int`  |
| `Texture2D`        | `float2`     | `int3` (xy + mip)     | `uint2`            | `int2` |
| `Texture2DArray`   | `float3`     | `int4`                | `uint3`            | `int2` |
| `Texture3D`        | `float3`     | `int4` (xyz + mip)    | `uint3`            | `int3` |
| `TextureCube`      | `float3`     | -                     | -                  | -      |
| `TextureCubeArray` | `float4`     | -                     | -                  | -      |
| `Texture2DMS`      | -            | `int2` + `int` sample | `uint2`            | `int2` |
| `Texture2DMSArray` | -            | `int3` + `int` sample | `uint3`            | -      |
| `RWTexture1D`      | -            | `int`                 | `uint`             | -      |
| `RWTexture1DArray` | -            | `int2`                | `uint2`            | -      |
| `RWTexture2D`      | -            | `int2`                | `uint2`            | -      |
| `RWTexture2DArray` | -            | `int3`                | `uint3`            | -      |
| `RWTexture3D`      | -            | `int3`                | `uint3`            | -      |

A dash indicates the method is not available on that type.

Scalar arguments (bias, LOD, compare value, clamp) must be `float`. The DDX and
DDY arguments to `SampleGrad` and `SampleCmpGrad` are float vectors matching the
resource's coordinate dimensionality (e.g., `float2` for `Texture2D`, `float3`
for `Texture3D`).

##### GatherCmp Component Restriction (Vulkan / SPIR-V)

On the Vulkan target, `GatherCmp` operations only support component 0 (Red).
`GatherCmpGreen`, `GatherCmpBlue`, and `GatherCmpAlpha` are rejected.
This is because SPIR-V's [OpImageDrefGather] does not have a Component operand
and always gathers component 0.

[OpImageDrefGather]: https://registry.khronos.org/SPIR-V/specs/unified1/SPIRV.html#OpImageDrefGather

##### Shader Stage and Shader Model Requirements

The following methods require derivative support: `Sample`, `SampleBias`,
`SampleCmp`, `SampleCmpBias`, `CalculateLevelOfDetail`, and
`CalculateLevelOfDetailUnclamped`. They are not valid in vertex, hull, domain,
geometry, or ray tracing shader stages. In compute, mesh, and amplification
shaders they require [SM 6.6 or greater][sm66-derivatives].
Methods that take an explicit LOD or explicit gradients (`SampleLevel`,
`SampleGrad`, `SampleCmpLevelZero`, `SampleCmpLevel`, `SampleCmpGrad`) do not
require derivatives.

Clang will diagnose use of derivative-requiring methods in unsupported shader
stages at the sema level using [availability attributes][availability-attributes]).
This differs from DXC which defers the rejection of `Sample`, `SampleBias`,
`SampleCmp`, and `SampleCmpBias` in unsupported shaders to the DXIL validator
via [`ValidateDerivativeOp`].

Some texture methods require later shader models. `SampleCmpLevel` and
`GatherRaw` require SM 6.7 ([`AdvancedTextureOps`]).
`SampleCmpBias`, `SampleCmpGrad`, and the use of `CalculateLevelOfDetail` with a
`SamplerComparisonState` require SM 6.8 ([`SampleCmpGradientOrBias`]).
All other texture methods are available from SM 6.0.

[sm66-derivatives]: https://microsoft.github.io/DirectX-Specs/d3d/HLSL_ShaderModel6_6.html#derivatives
[availability-attributes]: 0001-availability-diagnostics.md
[`ValidateDerivativeOp`]: https://github.com/microsoft/DirectXShaderCompiler/blob/1e4181c0f4cede851b9fa67a017717135849ba3d/lib/DxilValidation/DxilValidation.cpp#L402-L412
[`AdvancedTextureOps`]: https://microsoft.github.io/DirectX-Specs/d3d/HLSL_SM_6_7_Advanced_Texture_Ops.html
[`SampleCmpGradientOrBias`]: https://microsoft.github.io/hlsl-specs/proposals/0014-expanded-comparison-sampling/

### HLSL Builtin Interface

This section details the parameters for the Clang builtins. The `Coord`,
`Offset`, `DDX`, and `DDY` parameter types vary by resource dimensionality as
described in the [Coordinate and Argument Validation](#coordinate-and-argument-validation)
section. Optional parameters are indicated. If an optional parameter is not
provided, a default value of 0 is used.

- `T __builtin_hlsl_resource_sample(Handle, Sampler, floatN Coord, intN Offset = 0)`
- `T __builtin_hlsl_resource_sample_bias(Handle, Sampler, floatN Coord, float Bias, intN Offset = 0)`
- `T __builtin_hlsl_resource_sample_grad(Handle, Sampler, floatN Coord, floatN DDX, floatN DDY, intN Offset = 0)`
- `T __builtin_hlsl_resource_sample_level(Handle, Sampler, floatN Coord, float LOD, intN Offset = 0)`
- `float __builtin_hlsl_resource_sample_cmp(Handle, Sampler, floatN Coord, float CompareValue, intN Offset = 0)`
- `float __builtin_hlsl_resource_sample_cmp_level_zero(Handle, Sampler, floatN Coord, float CompareValue, intN Offset = 0)`
- `T __builtin_hlsl_resource_load_level(Handle, intN+1 CoordWithMip, intN Offset = 0)`
- `T __builtin_hlsl_resource_load_ms(Handle, intN Coord, int SampleIndex, intN Offset = 0)`
- `float4 __builtin_hlsl_resource_gather(Handle, Sampler, floatN Coord, int Component, intN Offset = 0)`
- `float4 __builtin_hlsl_resource_gather_cmp(Handle, Sampler, floatN Coord, float CompareValue, int Component, intN Offset = 0)`
- `float __builtin_hlsl_resource_calculate_lod(Handle, Sampler, floatN Coord)`
- `float __builtin_hlsl_resource_calculate_lod_unclamped(Handle, Sampler, floatN Coord)`
- `float2 __builtin_hlsl_resource_get_sample_position(Handle, uint SampleIndex)`
- For `GetDimensions` intrinsics, see
  [0033 - Resource GetDimensions](0033-resources-get-dimensions.md).

### Codegen

#### Builtin Lowering

The HLSL builtins used in the record type implementation are lowered to
target-specific LLVM intrinsics in Clang codegen. The naming convention follows
[0014 - Consistent Naming for DX Intrinsics](0014-consistent-naming-for-dx-intrinsics.md).

The `__builtin_hlsl_resource_load_level` builtin handles non-multisampled
texture loads. The mip level is packed into the last component of the coordinate
vector (e.g., `int2` for a 1D texture `(x, mip)`, `int3` for 2D `(x, y, mip)`,
`int4` for 3D `(x, y, z, mip)`), and `Offset` defaults to 0 if not provided.
For multisampled textures, the `__builtin_hlsl_resource_load_ms` builtin is
used, which takes the sample index as a separate parameter.

The LLVM intrinsics will be overloaded on the return type and the types of their
arguments (e.g., coordinates, offsets, derivatives). This avoids the need for
distinct intrinsic names for each texture dimension or type.

| HLSL Builtin                                      | LLVM Intrinsic                                                                   |
| :------------------------------------------------ | :------------------------------------------------------------------------------- |
| `__builtin_hlsl_resource_sample`                  | `llvm.<target>.resource.sample`<br>`llvm.<target>.resource.sample.clamp`         |
| `__builtin_hlsl_resource_sample_bias`             | `llvm.<target>.resource.samplebias`<br>`llvm.<target>.resource.samplebias.clamp` |
| `__builtin_hlsl_resource_sample_grad`             | `llvm.<target>.resource.samplegrad`<br>`llvm.<target>.resource.samplegrad.clamp` |
| `__builtin_hlsl_resource_sample_level`            | `llvm.<target>.resource.samplelevel`                                             |
| `__builtin_hlsl_resource_sample_cmp`              | `llvm.<target>.resource.samplecmp`<br>`llvm.<target>.resource.samplecmp.clamp`   |
| `__builtin_hlsl_resource_sample_cmp_level_zero`   | `llvm.<target>.resource.samplecmplevelzero`                                      |
| `__builtin_hlsl_resource_load_level`              | `llvm.<target>.resource.load.level`                                              |
| `__builtin_hlsl_resource_load_ms`                 | `llvm.<target>.resource.load.ms`                                                 |
| `__builtin_hlsl_resource_gather`                  | `llvm.<target>.resource.gather`                                                  |
| `__builtin_hlsl_resource_gather_cmp`              | `llvm.<target>.resource.gathercmp`                                               |
| `__builtin_hlsl_resource_calculate_lod`           | `llvm.<target>.resource.calculatelod`                                            |
| `__builtin_hlsl_resource_calculate_lod_unclamped` | `llvm.<target>.resource.calculatelod`                                            |
| `__builtin_hlsl_resource_get_sample_position`     | `llvm.<target>.resource.texturesamplepos`                                        |

- **Front-end**: Clang emits `llvm.dx.*` or `llvm.spv.*` intrinsics based on the
  target. The `<target>` in the table above is replaced by `dx` or `spv`
  respectively.
- **Backend (DXIL)**: The `llvm.dx.resource.*` intrinsics are lowered to DXIL
  operations (e.g., `dx.op.sample`). Handle arguments are translated to
  `dx.Texture` and `dx.Sampler` types.

#### DXIL Translation

The following table shows the translation from the LLVM intrinsics to the DXIL
operations.

| LLVM Intrinsic                                                       | DXIL Op                                   |
| :------------------------------------------------------------------- | :---------------------------------------- |
| `llvm.dx.resource.sample`<br>`llvm.dx.resource.sample.clamp`         | `dx.op.sample` (60)                       |
| `llvm.dx.resource.samplebias`<br>`llvm.dx.resource.samplebias.clamp` | `dx.op.sampleBias` (61)                   |
| `llvm.dx.resource.samplegrad`<br>`llvm.dx.resource.samplegrad.clamp` | `dx.op.sampleGrad` (63)                   |
| `llvm.dx.resource.samplelevel`                                       | `dx.op.sampleLevel` (62)                  |
| `llvm.dx.resource.samplecmp`<br>`llvm.dx.resource.samplecmp.clamp`   | `dx.op.sampleCmp` (64)                    |
| `llvm.dx.resource.samplecmplevelzero`                                | `dx.op.sampleCmpLevelZero` (65)           |
| `llvm.dx.resource.load.level`                                        | `dx.op.textureLoad` (66)                  |
| `llvm.dx.resource.load.ms`                                           | `dx.op.textureLoad` (66)                  |
| `llvm.dx.resource.gather`                                            | `dx.op.textureGather` (73)                |
| `llvm.dx.resource.gathercmp`                                         | `dx.op.textureGatherCmp` (74)             |
| `llvm.dx.resource.calculatelod`                                      | `dx.op.calculateLOD` (81)                 |
| `llvm.dx.resource.texturesamplepos`                                  | `dx.op.texture2DMSGetSamplePosition` (75) |

#### SPIR-V Translation

The following table shows the translation from the LLVM intrinsics to the SPIR-V
instructions.

| LLVM Intrinsic                                                         | SPIR-V Instruction                                                                 |
| :--------------------------------------------------------------------- | :--------------------------------------------------------------------------------- |
| `llvm.spv.resource.sample`<br>`llvm.spv.resource.sample.clamp`         | `OpImageSampleImplicitLod`<br>with `MinLod` operand if clamped                     |
| `llvm.spv.resource.samplebias`<br>`llvm.spv.resource.samplebias.clamp` | `OpImageSampleImplicitLod` with `Bias` operand<br>with `MinLod` operand if clamped |
| `llvm.spv.resource.samplegrad`<br>`llvm.spv.resource.samplegrad.clamp` | `OpImageSampleExplicitLod` with `Grad` operand<br>with `MinLod` operand if clamped |
| `llvm.spv.resource.samplelevel`                                        | `OpImageSampleExplicitLod` with `Lod` operand                                      |
| `llvm.spv.resource.samplecmp`<br>`llvm.spv.resource.samplecmp.clamp`   | `OpImageSampleDrefImplicitLod`<br>with `MinLod` operand if clamped                 |
| `llvm.spv.resource.samplecmplevelzero`                                 | `OpImageSampleDrefExplicitLod` with `Lod` 0                                        |
| `llvm.spv.resource.load.level`                                         | `OpImageFetch`                                                                     |
| `llvm.spv.resource.load.ms`                                            | `OpImageFetch` with `Sample` image operand                                         |
| `llvm.spv.resource.gather`                                             | `OpImageGather`                                                                    |
| `llvm.spv.resource.gathercmp`                                          | `OpImageDrefGather`                                                                |
| `llvm.spv.resource.calculatelod`                                       | `OpImageQueryLod`                                                                  |
| `llvm.spv.resource.texturesamplepos`                                   | Emulated                                                                           |

The intrinsic `llvm.spv.resource.texturesamplepos` is not directly supported in
Vulkan, but it is emulated by using a lookup table of standard sample positions.
The implementation works as follows:

1.  **Query Sample Count**: The sample count of the texture is queried using
    `OpImageQuerySamples`.
2.  **Select Position Array**: Based on the sample count, a specific constant
    array of sample positions is selected.
    - **Count 1**: Returns `(0, 0)`
    - **Count 2**:
      - 0: `(0.25, 0.25)`
      - 1: `(-0.25, -0.25)`
    - **Count 4**:
      - 0: `(-0.125, -0.375)`
      - 1: `(0.375, -0.125)`
      - 2: `(-0.375, 0.125)`
      - 3: `(0.125, 0.375)`
    - **Count 8**:
      - 0: `(0.0625, -0.1875)`
      - 1: `(-0.0625, 0.1875)`
      - 2: `(0.3125, 0.0625)`
      - 3: `(-0.1875, -0.3125)`
      - 4: `(-0.3125, 0.3125)`
      - 5: `(-0.4375, -0.0625)`
      - 6: `(0.1875, 0.4375)`
      - 7: `(0.4375, -0.4375)`
    - **Count 16**:
      - 0: `(0.0625, 0.0625)`
      - 1: `(-0.0625, -0.1875)`
      - 2: `(-0.1875, 0.125)`
      - 3: `(0.25, -0.0625)`
      - 4: `(-0.3125, -0.125)`
      - 5: `(0.125, 0.3125)`
      - 6: `(0.3125, 0.1875)`
      - 7: `(0.1875, -0.3125)`
      - 8: `(-0.125, 0.375)`
      - 9: `(0, -0.4375)`
      - 10: `(-0.25, -0.375)`
      - 11: `(-0.375, 0.25)`
      - 12: `(-0.5, 0)`
      - 13: `(0.4375, -0.25)`
      - 14: `(0.375, 0.4375)`
      - 15: `(-0.4375, -0.5)`
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

- **Sample Methods**: Tests `Sample`, `SampleBias`, `SampleGrad`, `SampleLevel`.
- **Comparison Sampling**: Tests `SampleCmp`, `SampleCmpLevelZero`.
- **Load**: Tests `Load` and `operator[]`.
- **Gather**: Tests `Gather` and its variants.
- **Dimensions**: Tests `GetDimensions`.
- **LOD Calculation**: Tests `CalculateLevelOfDetail`.
- **Multisample**: Tests `GetSamplePosition` (DXIL only) and `Load` on MS
  textures.

#### Detailed Testing Example: SampleLevel

We will use `SampleLevel` on a `Texture2D` as a representative example of how we
verify these methods. The goal is to prove the compiler generates the correct
instruction with the correct arguments. We do not need to test every possible
combination of texture formats or dimensions, nor do we need to verify the
hardware's texture filtering hardware in depth.

**Test Strategy:**

1.  **Sampler Configuration:** Create two distinct samplers.
    - `Samp1`: `MinFilter=Linear`, `MagFilter=Nearest`.
    - `Samp2`: `MinFilter=Nearest`, `MagFilter=Linear` (or simply different
      address modes/border colors to distinguish).
    - By using a specific sampler and getting the expected filtering result, we
      verify the correct sampler handle was passed.
2.  **Texture Setup:** Create a simple 2x2 texture with distinct colors for each
    quadrant:
    - (0,0) Red, (1,0) Green, (0,1) Blue, (1,1) White.
3.  **LOD Verification:**
    - Call `SampleLevel` with different LOD values using the same sampler and
      coordinates. Verify that the filtering results change as expected (e.g.,
      switching between magnification and minification).
4.  **Coordinate Verification:**
    - Sample at different UV locations. Verify that the returned colors match
      the expected texels at those locations.
5.  **Non-Literal Parameter Verification:**
    - Pass the LOD value from a runtime variable (e.g., loaded from a buffer).
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
