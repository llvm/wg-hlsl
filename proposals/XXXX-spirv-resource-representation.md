<!-- {% raw %} -->

# HLSL resources in SPIR-V

*   Proposal: [NNNN](NNNN-spirv-resource-representation.md)
*   Author(s): [Steven Perron](https://github.com/s-perron)
*   Status: **Design In Progress**

*During the review process, add the following fields as needed:*

*   PRs: [#114273](https://github.com/llvm/llvm-project/pull/114273),
    [#111052](https://github.com/llvm/llvm-project/pull/111052),
    [#111564](https://github.com/llvm/llvm-project/pull/111564),
    [#115178](https://github.com/llvm/llvm-project/pull/115178)

## Introduction

There is a need to represent the HLSL resources in llvm-ir in a way that the
SPIR-V backend is able to create the correct code. We have already done some
implementation work for `Buffer` and `RWBuffer`. This was done as a
proof-of-concept, and now we needed to determine how the other resource types
will be represented.

## Motivation

The HLSL resources are fundamental to HLSL, and they are required in a Vulkan
implementation.

## Proposed solution

We want to match the general solution proposed in
[0006-resource-representations.md](0006-resource-representations.md). The
`@llvm.spv.handle.fromBinding` intrinsic will be used to get a handle to the
resource. It will return a target type to represent the handle. Then other
intrinsics will be used to access the resource using the handle. Previous
proposals left open what the target types should be for SPIR-V.

The general pattern for the solution will be that `@llvm.spv.handle.fromBinding`
will return a SPIR-V pointer to a type `T`. The type for `T` will be detailed
when discusses each HLSL resource type. The SPIR-V backend will create a global
variable with type `T` if `range_size` is 1, and `T[range_size]` otherwise.

The reason we want `@llvm.spv.handle.fromBinding` to return a pointer is to make
it easier to satisfy the SPIR-V requirements in the
[Universal Validation Rules](https://registry.khronos.org/SPIR-V/specs/unified1/SPIRV.html#_universal_validation_rules).
Specifically,

> All OpSampledImage instructions, or instructions that load an image or sampler
> reference, must be in the same block in which their Result <id> are consumed.

It is the responsibility of the intrinsics that use the handles to load the
images and samplers.

The following sections will reference table 4 in the
[shader resrouce interface](https://docs.vulkan.org/spec/latest/chapters/interfaces.html#interfaces-resources)
for Vulkan.

### Textures and typed buffers

All of these resource types are represented using an image type in SPIRV. The
`Texture*` types are implemented as sampled images. the `RWTexture*` types are
implemented as storage images. `Buffer` is implemented as a uniform buffer, and
`RWBuffer` is implemented as a storage buffer.

For these cases the return type from `@llvm.spv.handle.fromBinding` would be:

```llvm-ir
target("spirv.Pointer", 0 /* UniformConstantStorageClass */, target("spirv.Image", ...))
```

The details of the `spirv.Image` type depend on the specific declaration.

TODO: We need to determine the image format.

### Structured buffers and texture buffers

All structured buffers and texture buffers are represented as storge buffers in
SPIR-V. The Vulkan documentation has two ways to represent a storage buffer. The
first representation was removed in SPIR-V 1.3 (Vulkan 1.1). We will generate
only the second representation.

For these cases the return type from `@llvm.spv.handle.fromBinding` for
`RWStructuredBuffer<T>` would be:

```llvm-ir
target("spirv.Pointer", 12 /* StorageBuffer */, T')
```

Where `T' = struct { T t[]; }`.

For `StructuredBuffer<T>`,

```llvm-ir
target("spirv.Pointer", 12 /* StorageBuffer */, const T')
```

TODO: We need to determine how the Block decoration will be added. The current
idea will have clang describe the type in detail, which means that clang needs a
way to say that the type `T'` requires the decoration. There is a
`spirv.Decoration` metadata, but that works on global variable only at this
time. We could have the target spirv type access the metadata node as an
operand. This interacts with the implementation of `vk::ext_decorate`, which
will have to be able to apply decoration to members of types.

TODO: We need to determine what the layout of the struct should be. Will we
support multiple layout as we do in DXC? This could be communicated to the back
end by adding the decorations to the type in the same way as the previous todo.

Note: We are in the middle of implementing `vk::SpirvType` in clang. That should
add a way to implement the target types without adding a specific
`spirv.Pointer` target type.

### Constant buffers

Constant buffers are implemented as uniform buffers. They will have the exact
same representation as a structured buffer except that the storage class will be
`Uniform` instead of `UniformConstant`.

### Samplers

For these cases the return type from `@llvm.spv.handle.fromBinding` would be:

```llvm-ir
target("spirv.Pointer", 0 /* UniformConstantStorageClass */, target("spirv.Sampler"))
```

This is the same for a `SamplerState` and `SamplerComparisonState`.

### Byte address buffers

If
[untyped pointers](https://htmlpreview.github.io/?https://github.com/KhronosGroup/SPIRV-Registry/blob/main/extensions/KHR/SPV_KHR_untyped_pointers.html)
are available, we will want to use the untyped pointers. However, if they are
not available, we will need to represent it as an array of integers, as is done
in DXC.

TODO: I'm thinking it is the responsibility of SPIRVTargetInfo to make this
decision.

If
[untyped pointers](https://htmlpreview.github.io/?https://github.com/KhronosGroup/SPIRV-Registry/blob/main/extensions/KHR/SPV_KHR_untyped_pointers.html)
are available, then the return type from `@llvm.spv.handle.fromBinding` would
be:

```llvm-ir
target("spirv.UntypedPointer", 12 /* StorageBuffer */)
```

If untyped pointers are not available, then the return type from
`@llvm.spv.handle.fromBinding` would be:

```llvm-ir
target("spirv.Pointer", 12 /* StorageBuffer */, { uint32_t[] })
```

TODO: Add the `block` decoration.

The intrinsics that use the ByteAddressBuffers will not change depending on the
type used. The SPIR-V backend should recognize the type and implement
accordingly.

### Rasterizer Order Views

If a resource is a rasterizer order view it will generate the exact same code as
its regular version except

1.  All uses of the resource will have a call site attribute indicating that
    this call must be part of the fragment shader's critical section. This is a
    new target attribute which will be call `spirv.InterlockedCritical`.
2.  The entry points (that reference directly or indirectly?) the ROVs will have
    an attribute `spirv.InterlockMode` which could have the value
    `SampleOrdered`, `SampleUnordered`, `PixelOrdered`, `PixelUnordered`,
    `ShadingRateOrdered`, or `ShadingRateUnordered`.

A pass similar to the `InvocationInterlockPlacementPass` pass in SPIR-V Tools
will be run in the SPIR-V backend to add instructions to begin and end the
critical section. This pass will be run after structurizing the llvm-ir, and
before ISel.

The SPIR-V backend will add the appropriate interlock execution mode to the
module based on the attribute on the entry point.

### Feedback textures

These resources do not have a straight-forward implementation in SPIR-V, and
they were not implemented in DXC. We will issue an error if these resource are
used when targeting SPIR-V.

## Detailed design

*The detailed design is not required until the feature is under review.*

This section should grow into a full specification that will provide enough
information for someone who isn't the proposal author to implement the feature.
It should also serve as the basis for documentation for the feature. Each
feature will need different levels of detail here, but some common things to
think through are:

*   Is there any potential for changed behavior?
*   Will this expose new interfaces that will have support burden?
*   How will this proposal be tested?
*   Does this require additional hardware/software/human resources?
*   What documentation should be updated or authored?

## Alternatives considered (Optional)

### Returning an image type in `@llvm.spv.handle.fromBinding`

We considered implementing returning the `target("spirv.Image", ...)` type from
`@llvm.spv.handle.fromBinding` instead of returning a pointer to the type. This
caused problems because the uses of the image have to be in the same basic
block, and, in general, the uses of the handle are not in the same basic block
as the call to `@llvm.spv.handle.fromBinding`.

To fix this, we would have to add a pass in the backend to fix up the problem by
replicating code, but this seems less desirable when we can generate the code
correctly.

It also makes the implementation of `@llvm.spv.handle.fromBinding` more
complicated because it will have to be treated differently than structured
buffers.

## Acknowledgments (Optional)

<!-- {% endraw %} -->
