---
title: "[NNNN] - Pre-passes in Offload Test Pipeline Descriptions"
params:
  authors:
    - Icohedron: Icohedron
  status: Under Consideration
---

## Introduction

This proposal introduces the concept of *pre-passes* to the offload test YAML
description. Pre-passes are an ordered list of pipelines that run before the
test pipeline in the same `offloader` invocation.

## Motivation

A test author sometimes needs a resource to hold values that only the GPU can
write before the test shader runs. The motivating case is a multisampled
texture: neither DirectX nor Vulkan can directly copy a buffer into one (a
Direct3D 12 [buffer footprint][d3d12-footprint] has no sample count, and
Vulkan [forbids it][vk-copy-ms]), so per-sample initial values can only be
written by a GPU pass: by rendering, or through a writable multisampled
texture on devices that support one.

Today an offload test cannot express that. One `offloader` run executes one
pipeline with one draw or dispatch, and the test YAML has no way of specifying
more pipelines that should run before it.

A pre-pass would also let a test generate a large input on the GPU instead of
listing every value in `Data`. A 256 × 256 texture has 65,536 texels; a
formula is easier to write, review and check than a list of that size.

## Proposed solution

A pipeline description gains an optional top-level `PrePasses` list. Each entry
is a pipeline with `Shaders`, `Bindings`, `DescriptorSets` and
`DispatchParameters`, with their [existing meaning][ots-yaml]. `Buffers` and
`Samplers` are shared by all passes, and `Results` stays top-level.
`Bindings.RenderTarget` gains a mapping form with `Name`, an optional
`ArrayIndex` and an optional `ArraySlice`, so that a pre-pass can write one
slice of a texture array or one element of a descriptor array.

### Example: generate a large texture

A compute pre-pass fills a 256 × 256 texture with the value `x + 256 * y` at
texel `(x, y)`. The test pipeline reads the same texture through a
shader-resource view. Every value is an integer below 2^24, so it is exact in
`float`.

```hlsl
// gen.hlsl: the pre-pass.
RWTexture2D<float> Tex : register(u0);

[numthreads(8, 8, 1)]
void main(uint3 ID : SV_DispatchThreadID) {
  Tex[ID.xy] = ID.x + 256.0 * ID.y;
}
```

```hlsl
// test.hlsl: the test pipeline.
Texture2D<float> Tex : register(t0);
RWBuffer<float> Out : register(u1);

[numthreads(1, 1, 1)]
void main() {
  Out[0] = Tex.Load(int3(0, 0, 0));                 // first texel
  Out[1] = Tex.Load(int3(255, 0, 0));               // end of row 0
  Out[2] = Tex.Load(int3(0, 1, 0));                 // start of row 1
  Out[3] = Tex.Load(int3(17, 200, 0));              // interior texel
  Out[4] = Tex.Load(int3(16, 200, 0), int2(1, 0));  // same texel, offset
  Out[5] = Tex.Load(int3(255, 255, 0));             // last texel
}
```

```yaml
---
PrePasses:                              # Proposed
  - Shaders:
      - Stage: Compute
        Entry: main
    DescriptorSets:
      - Resources:
        - Name: Tex
          Kind: RWTexture2D
          DirectXBinding: { Register: 0, Space: 0 }
          VulkanBinding: { Binding: 0 }
    DispatchParameters:
      DispatchGroupCount: [32, 32, 1]   # 256 / 8 in each dimension
Shaders:
  - Stage: Compute
    Entry: main
Buffers:
  - Name: Tex
    Format: Float32
    FillSize: 262144                    # 256 x 256 x 4 bytes
    OutputProps: { Width: 256, Height: 256, Depth: 1 }
  - Name: Out
    Format: Float32
    FillSize: 24                        # 6 x float
  - Name: ExpectedOut
    Format: Float32
    Data: [ 0.0, 255.0, 256.0, 51217.0, 51217.0, 65535.0 ]
DescriptorSets:
  - Resources:
    - Name: Tex
      Kind: Texture2D
      DirectXBinding: { Register: 0, Space: 0 }
      VulkanBinding: { Binding: 0 }
    - Name: Out
      Kind: RWBuffer
      DirectXBinding: { Register: 1, Space: 0 }
      VulkanBinding: { Binding: 1 }
Results:
  - Result: GeneratedTexture
    Rule: BufferExact
    Actual: Out
    Expected: ExpectedOut
...

# RUN: split-file %s %t
# RUN: %dxc_target -T cs_6_0 -Fo %t-gen.o %t/gen.hlsl
# RUN: %dxc_target -T cs_6_0 -Fo %t-test.o %t/test.hlsl
# RUN: %offloader %t/pipeline.yaml %t-gen.o %t-test.o
```

`Tex` is an unordered-access resource in the pre-pass and a shader resource in
the test pipeline. The runner creates one GPU resource with both usages and
makes the pre-pass writes visible before the test pipeline runs.

### Example: render one slice of a texture array

A raster pre-pass renders slice 1 of a `Texture2DArray`, and a compute test
pipeline loads both slices. The pre-pass draws one triangle that covers the
render target. Its pixel shader writes each pixel's `SV_Position`, so every
texel of slice 1 gets a different value that does not depend on the
orientation of clip space.

```hlsl
// test.hlsl: the test pipeline.
Texture2DArray<float4> Tex : register(t0);
RWBuffer<float4> Out : register(u1);

[numthreads(1, 1, 1)]
void main() {
  // Texture2DArray::Load takes int4(x, y, slice, mip).
  Out[0] = Tex.Load(int4(0, 0, 0, 0));
  Out[1] = Tex.Load(int4(1, 0, 0, 0));
  Out[2] = Tex.Load(int4(0, 1, 0, 0));
  Out[3] = Tex.Load(int4(1, 1, 0, 0));
  Out[4] = Tex.Load(int4(0, 0, 1, 0));
  Out[5] = Tex.Load(int4(1, 0, 1, 0));
  Out[6] = Tex.Load(int4(0, 1, 1, 0));
  Out[7] = Tex.Load(int4(1, 1, 1, 0));
}
```

```hlsl
// init.hlsl: the pre-pass.
float4 VSMain(uint ID : SV_VertexID) : SV_Position {
  // One triangle that covers the whole render target.
  const float2 Pos[3] = { float2(-1, 1), float2(3, 1), float2(-1, -3) };
  return float4(Pos[ID], 0, 1);
}

float4 PSMain(float4 Pos : SV_Position) : SV_Target {
  // Pixel (x, y) has its center at (x + 0.5, y + 0.5).
  return float4(Pos.xy, 10.0, 1.0);
}
```

```yaml
---
PrePasses:                              # Proposed
  - Shaders:
      - Stage: Vertex
        Entry: VSMain
      - Stage: Pixel
        Entry: PSMain
    Bindings:
      RenderTarget: { Name: Tex, ArraySlice: 1 }   # Proposed mapping form
    DescriptorSets: []
    DispatchParameters:
      VertexCount: 3                    # No vertex buffer; see SV_VertexID
Shaders:
  - Stage: Compute
    Entry: main
Buffers:
  - Name: Tex
    Format: Float32
    Channels: 4
    OutputProps: { Width: 2, Height: 2, Depth: 1, ArraySlices: 2 }
    FillSize: 128                       # 2 x 2 texels x 2 slices x float4
    FillValue: 7.0                      # The pre-pass overwrites slice 1
  - Name: Out
    Format: Float32
    Channels: 4
    FillSize: 128                       # 8 x float4
  - Name: ExpectedOut
    Format: Float32
    Channels: 4
    Data: [ 7.0, 7.0,  7.0, 7.0,   # [0] slice 0 (0,0): FillValue
            7.0, 7.0,  7.0, 7.0,   # [1] slice 0 (1,0)
            7.0, 7.0,  7.0, 7.0,   # [2] slice 0 (0,1)
            7.0, 7.0,  7.0, 7.0,   # [3] slice 0 (1,1)
            0.5, 0.5, 10.0, 1.0,   # [4] slice 1 (0,0): pre-pass values
            1.5, 0.5, 10.0, 1.0,   # [5] slice 1 (1,0)
            0.5, 1.5, 10.0, 1.0,   # [6] slice 1 (0,1)
            1.5, 1.5, 10.0, 1.0 ]  # [7] slice 1 (1,1)
DescriptorSets:
  - Resources:
    - Name: Tex
      Kind: Texture2DArray
      DirectXBinding: { Register: 0, Space: 0 }
      VulkanBinding: { Binding: 0 }
    - Name: Out
      Kind: RWBuffer
      DirectXBinding: { Register: 1, Space: 0 }
      VulkanBinding: { Binding: 1 }
Results:
  - Result: Slices
    Rule: BufferExact
    Actual: Out
    Expected: ExpectedOut
...

# RUN: split-file %s %t
# RUN: %dxc_target -T vs_6_0 -E VSMain -Fo %t-vs.o %t/init.hlsl
# RUN: %dxc_target -T ps_6_0 -E PSMain -Fo %t-ps.o %t/init.hlsl
# RUN: %dxc_target -T cs_6_0 -Fo %t-test.o %t/test.hlsl
# RUN: %offloader %t/pipeline.yaml %t-vs.o %t-ps.o %t-test.o
```

Slice 0 keeps its `FillValue`, which shows that the pre-pass wrote only the
selected slice. Slice 1 holds the pre-pass values, which shows that the
texture the pre-pass rendered is the texture the test shader reads.

Without `ArraySlice`, this description is an error: the render target names a
texture with more than one slice.

### Example: render one element of a descriptor array

A buffer with `ArraySize: 2` is a descriptor array of two textures. A raster
pre-pass renders only element 1, selected with `ArrayIndex`, and a compute test
pipeline loads both elements. The pre-pass draws one triangle that covers the
render target, and its pixel shader writes each pixel's `SV_Position`.

```hlsl
// test.hlsl: the test pipeline.
Texture2D<float4> Tex[2] : register(t0);
RWBuffer<float4> Out : register(u1);

[numthreads(1, 1, 1)]
void main() {
  Out[0] = Tex[0].Load(int3(0, 0, 0));
  Out[1] = Tex[0].Load(int3(1, 1, 0));
  Out[2] = Tex[1].Load(int3(0, 0, 0));
  Out[3] = Tex[1].Load(int3(1, 1, 0));
}
```

```hlsl
// init.hlsl: the pre-pass.
float4 VSMain(uint ID : SV_VertexID) : SV_Position {
  // One triangle that covers the whole render target.
  const float2 Pos[3] = { float2(-1, 1), float2(3, 1), float2(-1, -3) };
  return float4(Pos[ID], 0, 1);
}

float4 PSMain(float4 Pos : SV_Position) : SV_Target {
  // Pixel (x, y) has its center at (x + 0.5, y + 0.5).
  return float4(Pos.xy, 10.0, 1.0);
}
```

```yaml
---
PrePasses:                              # Proposed
  - Shaders:
      - Stage: Vertex
        Entry: VSMain
      - Stage: Pixel
        Entry: PSMain
    Bindings:
      RenderTarget: { Name: Tex, ArrayIndex: 1 }   # Proposed mapping form
    DescriptorSets: []
    DispatchParameters:
      VertexCount: 3                    # No vertex buffer; see SV_VertexID
Shaders:
  - Stage: Compute
    Entry: main
Buffers:
  - Name: Tex
    Format: Float32
    Channels: 4
    ArraySize: 2
    OutputProps: { Width: 2, Height: 2, Depth: 1 }
    FillSize: 64                        # Each element: 2 x 2 texels x float4
    FillValue: 7.0                      # The pre-pass overwrites element 1
  - Name: Out
    Format: Float32
    Channels: 4
    FillSize: 64                        # 4 x float4
  - Name: ExpectedOut
    Format: Float32
    Channels: 4
    Data: [ 7.0, 7.0,  7.0, 7.0,   # [0] element 0 (0,0): FillValue
            7.0, 7.0,  7.0, 7.0,   # [1] element 0 (1,1)
            0.5, 0.5, 10.0, 1.0,   # [2] element 1 (0,0): pre-pass values
            1.5, 1.5, 10.0, 1.0 ]  # [3] element 1 (1,1)
DescriptorSets:
  - Resources:
    - Name: Tex
      Kind: Texture2D
      DirectXBinding: { Register: 0, Space: 0 }
      VulkanBinding: { Binding: 0 }
    - Name: Out
      Kind: RWBuffer
      DirectXBinding: { Register: 1, Space: 0 }
      VulkanBinding: { Binding: 1 }
Results:
  - Result: Elements
    Rule: BufferExact
    Actual: Out
    Expected: ExpectedOut
...

# RUN: split-file %s %t
# RUN: %dxc_target -T vs_6_0 -E VSMain -Fo %t-vs.o %t/init.hlsl
# RUN: %dxc_target -T ps_6_0 -E PSMain -Fo %t-ps.o %t/init.hlsl
# RUN: %dxc_target -T cs_6_0 -Fo %t-test.o %t/test.hlsl
# RUN: %offloader %t/pipeline.yaml %t-vs.o %t-ps.o %t-test.o
```

Without `ArrayIndex`, this description is an error: the render target names a
buffer with `ArraySize` greater than 1.

### Shaders and compatibility

The test compiles every shader with `%dxc_target`, so pre-pass shaders run
through the compiler under test and are visible in the test file. Compiled
shaders are assigned to the pre-passes first, in list order, and then to the
test pipeline, the order in which the passes run. Tests without `PrePasses`
behave exactly as before.

## Detailed design

### Pipeline description schema

* New optional top-level `PrePasses` list. Each entry supports `Shaders`,
  `Bindings`, `DescriptorSets` and `DispatchParameters`.
* `Buffers` and `Samplers` are shared by all passes. `Results` stays
  top-level. Other fields (stencil state, push constants, runtime settings)
  apply to the test pipeline only.
* Descriptions without `PrePasses` parse and behave unchanged.

### Pipeline kinds and validation

* A pre-pass is a compute pipeline or a raster pipeline with vertex or mesh
  shaders.
* Each pre-pass is validated with the same per-kind and stage-combination
  rules as the test pipeline.
* Depth and stencil are disabled in pre-passes.

### Compiled shader assignment

The `offloader` assigns positional compiled shaders in the order the passes
run: first to each pre-pass's `Shaders` in list order, then to the test
pipeline's `Shaders`. The same file may appear several times. A description
without `PrePasses` assigns every file to the test pipeline, as today.

For the RUN line of the second example:

```text
%offloader %t/pipeline.yaml %t-vs.o %t-ps.o %t-test.o
                            |       |       `-> Shaders[0]: Compute
                            |       `-> PrePasses[0].Shaders[1]: Pixel
                            `-> PrePasses[0].Shaders[0]: Vertex
```

### Buffers shared across passes

All passes share the same buffers: every pass that names a buffer uses the
same GPU resources. A buffer's *role* in a pass is how that pass binds it: as a
render target, a vertex buffer, or a descriptor of a given kind (shader
resource, unordered access, constant buffer). The resource's usage is the
union of its roles across passes. The runner reports an error before any GPU
work when the buffer's format does not support that combined usage.

The runner already describes a texture's usage as a bitmask,
[`TextureUsage`][ots-usage], and maps it to Direct3D 12 resource flags and
Vulkan image usage. Today a texture gets the bit of its one role. With
pre-passes, the runner ORs the bits of every pass that names the buffer:

| Role in a pass   | `TextureUsage` | Direct3D 12 resource flag                    | Vulkan image usage                    |
|------------------|----------------|----------------------------------------------|---------------------------------------|
| Shader resource  | `Sampled`      | none                                         | `VK_IMAGE_USAGE_SAMPLED_BIT`          |
| Unordered access | `Storage`      | `D3D12_RESOURCE_FLAG_ALLOW_UNORDERED_ACCESS` | `VK_IMAGE_USAGE_STORAGE_BIT`          |
| Render target    | `RenderTarget` | `D3D12_RESOURCE_FLAG_ALLOW_RENDER_TARGET`    | `VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT` |

In the first example, `Tex` is `Sampled | Storage`; in the second, it is
`Sampled | RenderTarget`. The format check uses `D3D12_FEATURE_FORMAT_SUPPORT`
on Direct3D 12 and `vkGetPhysicalDeviceFormatProperties` on Vulkan.

Today the runner creates a render target as its own texture, separate from the
texture that a descriptor naming the same buffer gets. With one pipeline per
run, it makes no difference. With pre-passes, a later pass will need to be able
to read what an earlier pass rendered, so the render target and the descriptor
have to refer to the same texture. A render target starts with its buffer's
initial data and is never cleared, so it keeps what earlier passes wrote.

### Render-target element and slice selection

`Bindings.RenderTarget` keeps its scalar form (a buffer name) and gains a
mapping form with `Name`, an optional `ArrayIndex` and an optional
`ArraySlice`. `ArrayIndex` selects one of the `ArraySize` textures of a
descriptor array; `ArraySlice` selects one of the `ArraySlices` layers within
it. The mapping form is the same in every pass, including the test pipeline.
A pass renders into exactly one slice of one texture through a single-slice
render-target view.

Before any GPU work, validation rejects:

* an `ArraySlice` that is out of range or used on a non-array texture;
* an `ArrayIndex` that is out of range, or used on a buffer with
  `ArraySize: 1`, even when it is 0;
* a `RenderTarget` without a selector that its buffer needs: `ArrayIndex` when
  `ArraySize` is greater than 1, or `ArraySlice` when `ArraySlices` is greater
  than 1.

`ArrayIndex` and `ArraySlice` may appear together and are validated
independently. For example element 1, slice 2 of a `Texture2DArray`
descriptor array:

```yaml
RenderTarget:
  Name: Tex
  ArrayIndex: 1
  ArraySlice: 2
```

This render target selection would be expressed in Direct3D 12 and Vulkan as:

```cpp
// Direct3D 12
D3D12_RENDER_TARGET_VIEW_DESC Desc = {};
Desc.Format = Format;
Desc.ViewDimension = D3D12_RTV_DIMENSION_TEXTURE2DARRAY;
Desc.Texture2DArray.FirstArraySlice = 2;  // ArraySlice
Desc.Texture2DArray.ArraySize = 1;
Device->CreateRenderTargetView(Elements[1], &Desc, Handle);  // ArrayIndex

// Vulkan
VkImageViewCreateInfo Info = {VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO};
Info.image = Elements[1];  // ArrayIndex
Info.viewType = VK_IMAGE_VIEW_TYPE_2D;
Info.format = Format;
Info.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1,
                         2, 1};  // ArraySlice
```

Selecting an element or a slice limits only where a pass renders. The test
pipeline still reads back the whole buffer, including every slice and element.

### Execution and synchronization

After the runner copies each buffer's initial data to the GPU, it records the
pre-passes in list order, and then the test pipeline into one command list or
command buffer. Between passes, the runner inserts barriers to prevent data
hazards on shared resources. When a resource changes role, the barrier also
transitions the resource to the state or layout of its new role.

For `Tex` in the second example:

| Step           | Role of `Tex`           | Direct3D 12 state                                | Vulkan layout                              |
|----------------|-------------------------|--------------------------------------------------|--------------------------------------------|
| Initial upload | Copy destination        | `D3D12_RESOURCE_STATE_COPY_DEST`                 | `VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL`     |
| Pre-pass       | Render target           | `D3D12_RESOURCE_STATE_RENDER_TARGET`             | `VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL` |
| Test pipeline  | Compute shader resource | `D3D12_RESOURCE_STATE_NON_PIXEL_SHADER_RESOURCE` | `VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL` |

When consecutive passes both write a resource as unordered access, its state
does not change. The runner still inserts a barrier: a UAV barrier on
Direct3D 12 and a memory barrier on Vulkan.

### Documentation

The offload test suite documents the new YAML in a new `docs/PrePasses.md`,
next to its other feature documents such as [`docs/MSAA.md`][ots-msaa]. It
describes `PrePasses`, the order in which passes run, the order in which
compiled shader files are assigned, buffers shared across passes and the
`RenderTarget` mapping form with `ArrayIndex` and `ArraySlice`.

## Alternatives considered

### Runner-owned initialization

The multisampled-texture proposal ([llvm/wg-hlsl#489]) first let a test give a
multisampled texture per-sample initial values in `Data`, as for other
textures. The runner would then write those values itself:

* It copies the values into a staging buffer.
* For each sample and each array slice, it draws once with a one-bit sample
  mask. A built-in pixel shader reads the value of that sample from the staging
  buffer and writes it.
* The built-in shaders are compiled once, when the offload test suite is
  built, to DXIL and SPIR-V, and embedded in `offloader`.

An earlier pull request, [llvm/offload-test-suite#1079], implemented a variant
of this on Vulkan only. A built-in GLSL compute shader, precompiled to SPIR-V
and checked in, wrote the test data into each multisampled image through a
storage image before the test shader ran. It was closed without being merged.

This keeps tests short: the test YAML looks the same as for any other texture.
However, this approach was rejected for these reasons:

* **Hidden GPU work.** The draws and shaders that produce the initial values
  are not in the test file, so a reader cannot see or change them, and a
  failure in them looks like a failure of the test.
* **A fixed build-time compiler.** The built-in shaders would be compiled by
  one compiler chosen when the suite is built: DXC, or the Clang from the LLVM
  tree that the suite already builds against. That compiler is not necessarily
  the compiler under test.
* **Special cases in the runner.** A pixel shader's `SV_Target` type has to
  match the class of the render target's format, so the runner would need one
  built-in shader for each class: `float`, `int` and `uint`. It would also need
  a draw for each sample and its own capability checks. All of this would serve
  only multisampled textures.
* **No reuse.** Other GPU-written inputs, such as the generated texture in the
  first example, would need their own built-in mechanisms.

Pre-passes replace this with one general mechanism. The test writes the
initialization shaders and passes, and the compiler under test compiles them.

[llvm/wg-hlsl#489]: https://github.com/llvm/wg-hlsl/issues/489
[ots-yaml]: https://github.com/llvm/offload-test-suite/blob/0ae851f54960c063c8068e98478c76dabda2f7b4/README.md#yaml-pipeline-format
[d3d12-footprint]: https://learn.microsoft.com/en-us/windows/win32/api/d3d12/ns-d3d12-d3d12_subresource_footprint
[vk-copy-ms]: https://docs.vulkan.org/refpages/latest/refpages/source/vkCmdCopyBufferToImage.html#VUID-vkCmdCopyBufferToImage-dstImage-07973
[ots-msaa]: https://github.com/llvm/offload-test-suite/blob/0ae851f54960c063c8068e98478c76dabda2f7b4/docs/MSAA.md
[llvm/offload-test-suite#1079]: https://github.com/llvm/offload-test-suite/pull/1079
[ots-usage]: https://github.com/llvm/offload-test-suite/blob/0ae851f54960c063c8068e98478c76dabda2f7b4/include/API/Texture.h#L37-L42
