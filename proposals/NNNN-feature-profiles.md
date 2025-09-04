---
title: "[NNNN] - Feature Profiles"
params:
  authors:
    - llvm-beanz: Chris Bieneman
  status: Under Consideration
  sponsors:
    - llvm-beanz: Chris Bieneman
---

## Introduction

This proposal seeks to introduce a new more formalized way of specifying feature
profiles as a set of features to allow the compiler to utilize when generating
outputs. This proposal pairs stricter availability checks with explicit opt-in
mechanisms for optional features to help avoid the compiler introducing
unexpected dependencies on optional features which may not be widely supported.

## Motivation

Today DXC and Clang both implicitly and aggressively opt in to optional features
which may not be supported by all devices. This places a burden on users to
ensure that they are aware of the potential impacts on deployment for shaders
utilizing features which they may or may not have intended.

This feature addresses this problem by defining clear feature profiles derived
from DirectX Shader Models for DirectX targets and [Vulkan
Profiles](https://github.com/KhronosGroup/Vulkan-Profiles) for Vulkan, and
compiler features to enable opting in to optional features that layer on top of
the specified target profile.

## Proposed solution

The core of this proposal revolves around a new definition for "target profiles"
that the shader compiler will translate to available feature sets.

The target profile flag supported by DXC-compatible drivers as `-T` will be
extended to support a new wider set of profile values. The current profiles will
remain unchanged, which will imply a shader-model feature set and _all_ optional
features.

Target profiles should be flexible and easy to define. A target profile may
either be supported on a single target (e.g. a Vulkan profile may only be
supported when targeting Vulkan SPIRV), or it may be supported across all
targets. A target profile should specify a name and a set of target definitions
where each target definition is: a base target triple, a list of shader stages,
and a set of optional features on top of that base.

This pattern applies to existing target profiles. For example the following
would be a definition of the `6_0` profile for Shader Model 6.0:

```
ProfileName: 6_0
TargetDefinitions:
  - BaseTriple: dxil-shadermodel1.0
    Stages: [pixel, vertex, geometry, hull, domain, compute]
    RequiredFeatures:
      - Doubles
      - ComputeShadersPlusRawAndStructuredBuffers
      - UAVsAtEveryStage
      - Max64UAVs
      - MinimumPrecision
      - DX11_1_DoubleExtensions
      - DX11_1_ShaderExtensions
      - LEVEL9ComparisonFiltering
      - TiledResources
      - StencilRef
      - InnerCoverage
      - TypedUAVLoadAdditionalFormats
      - ROVs
      - ViewportAndRTArrayIndexFromAnyShaderFeedingRasterizer
      - WaveOps
      - Int64Ops
```

This pattern can also support more flexible profile definitions such as a
profile for Android 15 based on the Khronos-vended Vulkan profile:

```
ProfileName: Android15
TargetDefinitions:
  - BaseTriple: spirv-vulkan1.2
    Stages: [pixel, vertex, compute] # Not really sure what all Android supports...
    RequiredFeatures:
      - VK_KHR_maintenance5
      - VK_KHR_shader_float16_int8
      - VK_KHR_16bit_storage
      - VK_KHR_vertex_attribute_divisor
      - VK_EXT_custom_border_color
      - VK_EXT_device_memory_report
      - VK_EXT_external_memory_acquire_unmodified
      - VK_EXT_index_type_uint8
      - VK_EXT_load_store_op_none
      - VK_EXT_primitive_topology_list_restart
      - VK_EXT_provoking_vertex
      - VK_EXT_scalar_block_layout
      - VK_EXT_surface_maintenance1
      - VK_EXT_swapchain_maintenance1
      - VK_EXT_4444_formats
      - VK_ANDROID_external_format_resolve
      - VK_GOOGLE_surfaceless_query
```

Features marked "Required" are enabled in the compiler and available to use
without triggering diagnostics when the target profile is specified. Features
not explicitly required are treated as unavailable unless they have been
explicitly enabled by the user.

### Overriding Profile Settings

A target profile should initialize a set of base configurations. Those
configurations can be overridden with additional flags. Notably Clang's existing
`-triple` and `-target-feature` can be used to override the base triple or
enable and disable specific target features.

### Example Usage

```
clang-dxc -T cs_6_0 ...
```

Builds a compute shader for Shader Model 6.0, allowing all optional features of
SM 6.0 and earlier.

```
clang-dxc -T cs_Android15 ...
```

Builds a compute shader for Android 15, targeting SPIRV 1.2 and allowing the
required features supported by the Android 15 profile.

```
clang-dxc -T cs_DirectX_12_1 ...
```

Builds a compute shader for the DirectX 12_1 feature tier, targeting DXIL 1.0
and a defined set of optional features aligning with 12_1's required features
documented on
[learn.microsoft](https://learn.microsoft.com/en-us/windows/win32/direct3d12/hardware-feature-levels).


```
clang-dxc -T cs_DirectX_12_1 -target-feature +NativeLowPrecision ...
```

Builds a compute shader for the DirectX 12_1 feature tier, targeting DXIL 1.2
with 16-bit native types enabled, and a defined set of optional features
aligning with 12_1's required features documented on
[learn.microsoft](https://learn.microsoft.com/en-us/windows/win32/direct3d12/hardware-feature-levels).

```
clang-dxc -T cs_DirectX_12_1 -triple dxil-shadermodel6.4 ...
```

Builds a compute shader for the DirectX 12_1 feature tier, targeting DXIL 1.4
and a defined set of optional features aligning with 12_1's required features
documented on
[learn.microsoft](https://learn.microsoft.com/en-us/windows/win32/direct3d12/hardware-feature-levels).

## Outstanding Questions

* Should target profiles support a restricted set of optional features?
* Can we rely on using LLVM's target features capabilities to drive this?
* Should we support a `pragma` to enable features via source?
* Common profiles across runtimes?
* Should we have a format for user-defined profiles as input to the compiler?
