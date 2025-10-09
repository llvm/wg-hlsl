---
title: "[0033] - GetDimensions mapping to built-ins functions and LLVM intrinsics"
params:
  authors:
    - github_username: hekota
  status: Under Consideration
  sponsors:
    - github_username: hekota
---

## Introduction

All buffer and texture resources have a `GetDimensions` member function which
must be supported across all resource types. There are many different overloads
of this function. This proposal summarizes the variants and outlines how they
can be implemented in Clang using built-in functions, as well as how they map to
LLVM intrinsics.

## Motivation

`GetDimensions` member function on resource classes is part of the HLSL language
and we need to support it in Clang.

## Proposed solution

### Clang built-in functions

There are 54 `GetDimensions` member function overloads across all resource
classes, and that does not even include resource classes with rasterizer ordered
views (resources whose names start with `RasterizerOrdered*`).

We need to add a number of built-in functions to Clang to implement these. This
will most likely amount to one built-in function per unique argument list.
However, `GetDimensions` overloads that differ only by the types of their
arguments (namely, `uint` vs. `float`) can be consolidated under the same
built-in function, thereby greatly reducing the number of needed built-in
functions.

In Clang codegen, these built-in functions will be translated into one or more
LLVM intrinsics, depending on the target platform.

### Lowering to DXIL

For DXIL, all `GetDimensions` calls should be lowered to the
`dx.op.getDimensions` DXIL operation. This operation takes a resource handle and
a MIP level as inputs, and returns a struct containing four integers:

`%dx.types.Dimensions = type { i32, i32, i32, i32 }`.
 
Values in this struct correspond to the requested resource dimension values. The
exact mapping depends on the resource type and is documented
[here](https://github.com/microsoft/DirectXShaderCompiler/blob/main/docs/DXIL.rst#getdimensions).

While it would be possible to map this DXIL op to a single LLVM intrinsic for
all cases, it is cleaner and more maintainable from a design perspective to
define multiple LLVM intrinsics. Ideally, there would be one intrinsic for each
unique mapping of the values in the `dx.op.getDimensions`
[table](https://github.com/microsoft/DirectXShaderCompiler/blob/main/docs/DXIL.rst#getdimensions).

For `GetDimensions` overloads that require `float` outputs, Clang code
generation will insert the necessary conversions from `i32` to `float`.

### Lowering to SPIR-V

For SPIR-V, the specific instructions generated for a `GetDimensions` call
depend on both the resource type and the arguments of the member function. Based
on initial testing, the following SPIR-V operations are used:

- `OpImageQuerySize`
- `OpImageQuerySizeLod`
- `OpArrayLength`
- `OpImageQueryLevels`
- `OpImageQuerySamples`

SPIR-V code generation can either mirror the same set of LLVM intrinsics as DXIL
codegen, or define its own set of intrinsics corresponding to the specific
SPIR-V operations. The design below assumes the former approach.

## Detailed design

This section enumerates all `GetDimensions` member function overloads, grouping
them according to the similarity of their argument lists, the resource types
they operate on, and the corresponding SPIR-V operations generated for each
combination.

_Note: `$type1` refers to the type of the first argument, `$type2` to the second
argument, and so on. [uint|float] indicates that the type can be either `uint`
or `float`.

### Buffers

| Resource class | Overloads   | SPIR-V op |
|----------------|-------------|-----------|
|Buffer<br/>RWBuffer|GetDimensions(out uint dim)|OpImageQuerySize|
|ByteAddressBuffer<br/>RWByteAddressBuffer|GetDimensions(out uint dim)|OpArrayLength|
|StructuredBuffer<br/>RWStructuredBuffer<br/>AppendStructuredBuffer<br/>ConsumeStructuredBuffer|GetDimensions(out uint numStructs, out uint stride)|OpArrayLength|

These overloads will be implemented using built-in function

```c++
  void __builtin_hlsl_buffer_getdimensions(__hlsl_resource_t handle, uint &dim);
```

and

```c++
  void __builtin_hlsl_buffer_getstride(__hlsl_resource_t handle, uint &stride);
```
The `__builtin_hlsl_buffer_getstride` builtin will be implemented entirely by
Clang codegen and will not results in any LLVM intrinsic call.

The `__builtin_hlsl_buffer_getdimensions` built-in will be translated to
`llvm.{dx|spv}.resource.getdimensions.buffer` LLVM instrinsic that will look
like this:

```
i32 @llvm.dx.resource.getdimensions.buffer(target("dx.*",..) resource_handle)
i32 @llvm.spv.resource.getdimensions.buffer(target("spirv.*",..) resource_handle)
```

The SPIR-V lowerer can decide whether to use `OpImageQuerySize` or
`OpArrayLength` op based on `resource_handle` target type.

### Textures

| Resource class | Overloads   | SPIR-V op |
|----------------|-------------|-----------|
|Texture1D|GetDimensions(out [uint\|float] width)<br/>GetDimensions(uint mipLevel, out [uint\|float] width, out $type2 numberOfLevels)|OpImageQuerySizeLod<br/>+OpImageQueryLevels|
|Texture2D|GetDimensions(out [uint\|float] width, out $type1 height)<br/>GetDimensions(uint mipLevel, out [uint\|float] width, out $type2 height, out $type2 numberOfLevels)|OpImageQuerySizeLod<br/>+OpImageQueryLevels|
|Texture3D|GetDimensions(out [uint\|float] width, out $type1 height, out $type1 depth)<br/>GetDimensions(uint mipLevel, out [uint\|float] width, out $type2 height, out $type2 depth, out $type2 numberOfLevels)|OpImageQuerySizeLod<br/>+OpImageQueryLevels|
|TextureCUBE|GetDimensions(out [uint\|float] width, out $type1 height)<br/>GetDimensions(uint mipLevel, out [uint\|float] width, out $type2 height, out $type2 numberOfLevels)|OpImageQuerySizeLod<br/>+OpImageQueryLevels|
|RWTexture1D|GetDimensions(out [uint\|float] width)|OpImageQuerySize|
|RWTexture2D|GetDimensions(out [uint\|float] width, out $type1 height)|OpImageQuerySize|
|RWTexture3D|GetDimensions(out [uint\|float] width, out $type1 height, out $type1 depth)|OpImageQuerySize|

The built-in function for overloads that do not use the MIP levels will look like this:
```
void __builtin_hlsl_texture_getdimension(__hlsl_resource_t handle, [uint|float] &width)

void __builtin_hlsl_texture_getdimension(__hlsl_resource_t handle, [uint|float] &width, $type2 &height)

void __builtin_hlsl_texture_getdimension(__hlsl_resource_t handle, [uint|float] &width, $type2 &height, $type2 &depth)
```

And those that use MIP levels are:
```
void __builtin_hlsl_texture_getdimension_with_levels(__hlsl_resource_t handle, uint mip_level, [uint|float] &width,
                                                     $type3 &levels_count)

void __builtin_hlsl_texture_getdimension_with_levels(__hlsl_resource_t handle, uint mip_level, [uint|float] &width,
                                                     $type3 &height, $type3 &levels_count)

void __builtin_hlsl_texture_getdimension_with_levels(__hlsl_resource_t handle, uint mip_level, [uint|float] &width,
                                                     $type3 &height, $type3 &depth, $type3 &levels_count)
```

Clang codegen can inspect the dimension attribute on the handle type (design
TBD) to identify which combination of width, height, and depth values should be
expected and validated for each resource.

LLVM intrinsic design TBD later.

### Texture Arrays

| Resource class | Overloads   | SPIR-V op |
|----------------|-------------|-----------|
|Texture1DArray|GetDimensions(out [uint\|float] width, out $type1 elements)<br/>GetDimensions(in uint mipLevel, out [uint\|float] width, out $type2 elements, out $type2 numberOfLevels)|OpImageQuerySizeLod<br/>+OpImageQueryLevels|
|Texture2DArray|GetDimensions(out [uint\|float] width, out $type1 height, out $type1 elements)<br/>GetDimensions(in uint mipLevel, out [uint\|float] width, out $type1 height, out $type2 elements, out $type2 numberOfLevels)|OpImageQuerySizeLod<br/>+OpImageQueryLevels|
|TextureCUBEArray|GetDimensions(out [uint\|float] width, out $type1 height, out $type1 elements)<br/>GetDimensions(in uint mipLevel, out [uint\|float]width, out $type1 height, out $type2 elements, out $type2 numberOfLevels)|OpImageQuerySizeLod<br/>+OpImageQueryLevels|
|RWTexture1DArray|GetDimensions(out [uint\|float] width, out $type1 elements)|OpImageQuerySize|
|RWTexture2DArray|GetDimensions(out [uint\|float] width, out $type1 height, out $type1 elements)|OpImageQuerySize|

The built-in function for overloads that do not use the MIP levels will look like this:

```
void __builtin_hlsl_texturearray_getdimension(__hlsl_resource_t handle, [uint|float] &width, $type2 &elements)

void __builtin_hlsl_texturearray_getdimension(__hlsl_resource_t handle, [uint|float] &width, $type2 &height,
                                              $type3 &elements)

void __builtin_hlsl_texturearray_getdimension(__hlsl_resource_t handle, [uint|float] &width, $type2 &height,
                                              $type2 &depth, $type3 &elements)
```
And those that use MIP levels are:
```
void __builtin_hlsl_texturearray_getdimension_with_levels(__hlsl_resource_t handle, uint mip_level, [uint|float] &width,
                                              $type3 &elements, $type3 &levels_count)

void __builtin_hlsl_texturearray_getdimension_with_levels(__hlsl_resource_t handle, uint mip_level, [uint|float] &width,
                                              $type3 &height, $type3 &elements, $type3 &levels_count)

void __builtin_hlsl_texturearray_getdimension_with_levels(__hlsl_resource_t handle, uint mip_level, [uint|float] &width,
                                              $type3 &height, $type3 &depth, $type3 &elements, $type3 &levels_count)
```
Clang codegen can inspect the dimension attribute on the handle type (design
TBD) to identify which combination of width, height, and depth values should be
expected and validated for each resource.

LLVM intrinsic design TBD later.

### Multisampled Textures and Arrays

| Resource class | Overloads   | SPIR-V op |
|----------------|-------------|-----------|
|Texture2DMS|GetDimensions(out [uint\|float] width, out $type1 height, out $type2 numberOfSamples)|OpImageQuerySize<br/>+OpImageQuerySamples|
|RWTexture2DMS|GetDimensions(out [uint\|float] width, out $type1 height, out $type2 numberOfSamples)|OpImageQuerySize<br/>+OpImageQuerySamples<br/>_unimplemented in DXC_|
|Texture2DMSArray|GetDimensions(out [uint\|float] width, out $type1 height, out $type1 elements, out $type2 numberOfSamples)|OpImageQuerySize<br/>+OpImageQuerySamples|
|RWTexture2DMSArray|GetDimensions(out [uint\|float] width, out $type1 height, out $type1 elements, out $type2 numberOfSamples)|OpImageQuerySize<br/>+OpImageQuerySamples<br/>_unimplemented in DXC_|

The built-in function for multisampled texture overloads will look like this:

```
void __builtin_hlsl_texture_getdimension_ms(__hlsl_resource_t handle, [uint|float] &width, $type2 &height,
                                            $type2 &samples_count)
```

And for multisampled texture array overloads it will look like this:

```
void __builtin_hlsl_texturearray_getdimension_ms(__hlsl_resource_t handle, [uint|float] &width, $type2 &height,
                                                 $type2 &elements, $type2 &samples_count)
```

LLVM intrinsic design TBD later.

## Alternatives considered (Optional)

## Acknowledgments (Optional)
