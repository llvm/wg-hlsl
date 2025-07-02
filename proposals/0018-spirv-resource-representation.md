<!-- {% raw %} -->

# HLSL resources in SPIR-V

*   Proposal: [0018](0018-spirv-resource-representation.md)
*   Author(s): [Steven Perron](https://github.com/s-perron)
*   Status: **Design In Progress**

*During the review process, add the following fields as needed:*

*   PRs: [#114273](https://github.com/llvm/llvm-project/pull/114273),
    [#111052](https://github.com/llvm/llvm-project/pull/111052),
    [#111564](https://github.com/llvm/llvm-project/pull/111564),
    [#115178](https://github.com/llvm/llvm-project/pull/115178),
    [#144774](https://github.com/llvm/llvm-project/pull/144774)

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

The type for the handle will depend on the type of resource, and will be
detailed in the following sections.

The following sections will reference table 4 in the
[shader resource interface](https://docs.vulkan.org/spec/latest/chapters/interfaces.html#interfaces-resources)
for Vulkan.

### SPIR-V target types

There must be appropriate SPIR-V target types to represent the HLSL resources.
We could try to represent the resources using the exact SPIR-V type that will be
needed. The problem is that the HLSL resources does not map too closely with
SPIR-V.

Consider `StructuredBuffer`, `RWStructuredBuffer`,
`RasterizerOrderedStructuredBuffer`, `AppendStructureBuffer`, and
`ConsumeStructuredBuffer`. These resource types do not map directly to SPIR-V.
They have multiple implicit features that need to map to different SPIR-V:

1.  They all contain an array of memory that maps to a storage buffer.
2.  Other than `StructuredBuffer`, they all contain a separate counter variable
    that is its own storage buffer.
3.  The references to `RasterizerOrderedStructuredBuffer` are contained in
    implicit critical regions. In SPIR-V, explicit instructions are used to
    start and stop the critical region.

This makes it impossible to create a handle type that maps directly to a SPIR-V
type. For now, the counter variable will not be handled. We will create a target
type `spirv.VulkanBuffer` to represent a storage or uniform buffer:

```
target("spirv.VulkanBuffer", ElementType, StorageClass, IsWriteable)
```

`ElementType` is the type for the storage buffer array, and `StorageClass` is
the storage class for the array. `IsWriteable` is true if the resource can be
written to.

In the SPIR-V backend, there will be a legalization pass that will lower the
`spirv.VulkanBuffer` type to code closer to the SPIR-V to be generated:

1.  Calls to `@llvm.spv.resource.getpointer` will have the handle replaced by
    the handle of the array.
2.  If the type of the original handle is rasterizer ordered, all uses of
    `@llvm.spv.resource.getpointer` will be surrounded by instructions to begin
    and end the critical region.

A separate legalization pass will then move the critical region markers so that
they follow the rules required by the SPIR-V specification. This will be the
same as the
[`InvocationInterlockPlacementPass`](https://github.com/KhronosGroup/SPIRV-Tools/blob/682bcd51548e670811f1d03511968bb59a1157ce/source/opt/invocation_interlock_placement_pass.h)
pass in SPIR-V Tools.

The types for the buffers must have an
[explicit layout](https://registry.khronos.org/SPIR-V/specs/unified1/SPIRV.html#ExplicitLayout).
The layout information will be obtained from the DataLayout class:

1.  Struct offsets will come from `DataLayout::getStructLayout`, which returns
    the offset for each member.
2.  The array stride will be the size of the array elements. This assumes that
    structs have appropriate padding at the end to ensure its size is a multiple
    of its alignment.
3.  Matrix stride?
4.  Row major vs Col major?

It is Clang's responsibility to make sure that the data layout is set correctly,
and that the structs have the correct explicit padding for this to be correct.

### Textures and typed buffers

All of these resource types are represented using an image type in SPIRV. The
`Texture*` types are implemented as sampled images. The `RWTexture*` types are
implemented as storage images. `Buffer` is implemented as a uniform buffer, and
`RWBuffer` is implemented as a storage texel buffer.

For these cases the return type from `@llvm.spv.handle.fromBinding` would be the
image type matching the resource type:

```llvm-ir
target("spirv.Image", ...)
target("spirv.SignedImage", ...)
```

The details of the `spirv.*Image` type depend on the specific declaration.
Except for the image format, the value for each operand is given in the
[Mapping Resource Attributes to DXIL and SPIR-V](https://github.com/llvm/wg-hlsl/blob/main/proposals/0015-resource-attributes-in-dxil-and-spirv.md)
proposal. For all resource types other than `RWBuffer<T>` and `RWTexture*<T>`,
the image format will be `Unknown`.

Note that if `T` is a signed integer type, the the `spirv.SignedImage` type will
be used. Otherwise `spirv.Image` will be used. This allows the backend to
generate sampling operation that do a sign extend when necessary.

For `RWBuffer<T>` and `RWTexture*<T>` resource types, if the Vulkan version is
1.3 or later, the image format will be `Unknown`. This satisfies
[VUID-RuntimeSpirv-apiVersion-07954](https://docs.vulkan.org/spec/latest/appendices/spirvenv.html#VUID-RuntimeSpirv-apiVersion-07954)
and
[VUID-RuntimeSpirv-apiVersion-07955](https://docs.vulkan.org/spec/latest/appendices/spirvenv.html#VUID-RuntimeSpirv-apiVersion-07954).

Otherwise, the image format for those resource types will be determined by the
template type `T`, and will match the existing behaviour implemented in DXC.

Note that this creates a disconnect with the
[Universal Validation Rules](https://registry.khronos.org/SPIR-V/specs/unified1/SPIRV.html#_universal_validation_rules).
Specifically,

> All OpSampledImage instructions, or instructions that load an image or sampler
> reference, must be in the same block in which their Result <id> are consumed.

The image object is conceptually loaded at the location that
`@llvm.spv.handle.fromBinding` is called. There is nothing forcing this
intrinsic to be called in the same basic block in which it is used. It is the
responsibility of the backend to replicate the load in the basic block in which
it is used.

### Structured Buffers

The handle for structured buffers will be

| HLSL Resource Type                   | Handle Type                          |
| ------------------------------------ | ------------------------------------ |
| StructuredBuffer<T>                  | spirv.VulkanBuffer(T, StorageBuffer, |
:                                      : false)                               :
| RWStructuredBuffer<T>                | spirv.VulkanBuffer(T, StorageBuffer, |
:                                      : true)                                :
| RasterizerOrderedStructuredBuffer<T> | TODO                                 |
| AppendStructuredBuffer<T>            | spirv.VulkanBuffer(T, StorageBuffer, |
:                                      : true)                                :
| ConsumeStructuredBuffer<T>           | spirv.VulkanBuffer(T, StorageBuffer, |
:                                      : true)                                :

### Texture buffers

Texture buffers are implemented in SPIR-V as storage buffers. From a SPIR-V
perspective, this makes it the same as a `StructureBuffer`, and will be
represented the same way:

```
spirv.VulkanBuffer(T, StorageBuffer, false)
```

### Constant buffers

In SPIR-V, constant buffers are implemented as uniform buffers. The only
difference between a uniform buffer and storage buffer is the storage class.
Uniform buffers use the `Uniform` storage class. The handle type will be:

```
spirv.VulkanBuffer(T, Uniform, false, false)
```

### Samplers

The type of the handle for a sampler will be:

```llvm-ir
target("spirv.Sampler")
```

This is the same for a `SamplerState` and `SamplerComparisonState`.

### Byte address buffers

DXC represents byte address buffers as a storage buffer of 32-bit integers. The
problem with this is that loads and store require lots of data manipulation to
correctly handle the data. It also means we cannot do atomic operations unless
they are 32-bit operations.

Because of this limitation, we do not want Clang to enforce a particular
representation. Instead, we can represent the buffer as a buffer with a `void`
type. The backend indicates to the backend it can choose the representation, but
it is responsible for updating accessed to match the representation it chooses.

Note that if
[untyped pointers](https://htmlpreview.github.io/?https://github.com/KhronosGroup/SPIRV-Registry/blob/main/extensions/KHR/SPV_KHR_untyped_pointers.html)
are available, this will map naturally to untyped pointers.

| HLSL Resource Type                 | Handle Type                             |
| ---------------------------------- | --------------------------------------- |
| ByteAddressBuffer                  | spirv.VulkanBuffer(void, StorageBuffer, |
:                                    : false)                                  :
| RWByteAddressBuffer                | spirv.VulkanBuffer(void, StorageBuffer, |
:                                    : true)                                   :
| RasterizerOrderedByteAddressBuffer | TODO                                    |

### Feedback textures

These resources do not have a straight-forward implementation in SPIR-V, and
they were not implemented in DXC. We will issue an error if these resource are
used when targeting SPIR-V.

## Alternatives considered (Optional)

### Returning pointers as the handle

We considered making all handles return by `@llvm.spv.handle.fromBinding` to be
pointers to some type. For textures, it would return a pointer to the image
type.

This would have been nice because load of the image object would no longer be in
`@llvm.spv.handle.fromBinding` and would be in the intrinsic that uses the
handle. That would automatically make it in the same basic block as it use.

The problem is that this does not work well for structured buffers, because, as
far as HLSL is concerned, the handle for a structured buffer references two
resources as detailed above. There is no way to represent this properly.

Less important, but still worth mentioning, is that in SPIR-V, the image object
is the handle to the image. We chose the design the was the better match
conceptually. Replicating the load of the image object is not a difficult
problem to solve.

## Open Questions

1.  How will the binding for the counter resource be represented?

The design for the counter variable associated with structured buffer types is
not complete. However, there is one important restriction the Clang codegen does
not diverge too much from DXIL:

The storage for the storage buffer and the counter variable must be access
through the same handle. The intrinsics that use it will determine which
resource is being accessed.

They will have to somehow be added to the `resource.gethandlefrombinding`. They
cannot be added to the target type. If they were, the types for the resource
aliases would not match, causing problem in codegen. For example:

```c++
RWStructuredBuffer<int> a;

// The type for `b` handle will be different from `a`'s handle, because it
// needs a different counter var.
RWStructuredBuffer<int> b;

static RWStructuredBuffer<int> c; // What type should `c`'s be?

void main() {
  c = a; // It must match the type for a.
  c = b; // It must also match the type for b.
```

1.  Do we need `vk::image_format` for Vulkan 1.3 and later?

We need to determine whether we can deprecate the use of `vk::image_format` for
Vulkan 1.3 and later. We could potentially use unknown for all resource types.
We need to assess if there is any advantage to specifying a particular format.
If no advantage exists, then we should not attempt to support specific formats.

1.  Determine how to add the appropriate decorations for matrices.

If a matrix is part of a storage buffer, it must have an explicit layout with
MatrixStride and either RowMajor or ColMajor decorations. Because matrices are
not yet implemented, we cannot yet determine how these decorations will be
added.

<!-- {% endraw %} -->
