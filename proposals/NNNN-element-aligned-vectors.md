---
title: "[NNNN] - Element-aligned vectors"
params:
  authors:
    - bogner: Justin Bogner
  status: Under Consideration
---

* Issues:
  - [llvm/llvm-project#123868](https://github.com/llvm/llvm-project/issues/123968)
* PRs:
  - [#180617: [DataLayout] Add a specifier for element-aligned vectors](https://github.com/llvm/llvm-project/pull/180617)
  - [#180622: [DirectX] Specify element-aligned vectors](https://github.com/llvm/llvm-project/pull/180622)
  - [#180620: [clang][DirectX] Specify element-aligned vectors in TargetInfo](https://github.com/llvm/llvm-project/pull/180620)

## Introduction

Vectors in DirectX and SPIR-V are generally element-aligned, but this isn't
representable in LLVM's datalayout, and even if it were Clang makes assumptions
that vectors are naturally aligned without consulting the target at all.

## Motivation

The alignment of vectors affects how structs and arrays containing these types
are laid out in memory. These layouts need to be compatible with how DirectX
and Vulkan specify such objects are laid out, otherwise data placed in buffers,
textures, and cbuffers will be in the wrong place and shader programs won't
function correctly.

The issues around these types tend to mostly come up with 2- and 3-element
vectors, as 4-element vectors usually line up with 16-byte boundary related
language rules, so the fact that we treat them as overaligned isn't observable.

## Proposed solution

We propose a specification to LLVM's DataLayout string to say that vectors are
element-aligned by default, and a bit to Clang's TargetInfo to say that vectors
are element-aligned for a target. These will need to be kept in sync for a
given target, but this is already true for most of the values in Clang's
TargetInfo.

We can then update the DirectX and SPIR-V targets to use this specifier. 

For DirectX, the alignment rules for vector types are not explicitly
documented. However, element-alignment by default matches DXC behaviour and
driver expectations.

For SPIR-V, element-alignment is [specified in Vulkan] for both "Standard
Uniform Buffer Layout" and "Standard Storage Buffer Layout". Additionally,
element-alignment matches all four of DXC's options for [memory layout rules]
when emitting SPIR-V.

[specified in Vulkan]: https://registry.khronos.org/vulkan/specs/latest/html/vkspec.html#interfaces-resources-layout
[memory layout rules]: https://github.com/microsoft/DirectXShaderCompiler/blob/main/docs/SPIR-V.rst#memory-layout-rules

## Detailed design

- Add and document a "ve" specifier to the [Data Layout string], which
  specifies that vectors are element-aligned unless they have a more specific
  rule.
- Add a boolean value to `clang::TransferrableTargetInfo` saying that
  `VectorsAreElementAligned`.
- Update the DirectX and SPIR-V targets to specify both of these.

[Data Layout string]: https://llvm.org/docs/LangRef.html#langref-datalayout

## Alternatives considered

### Alternatives for how to specify element-alignment in Data Layout

There are a details about hwo we could specify element-alignment in the Data
Layout that we do not intend to pursue at this time:

- Alternative spellings to "ve"
- Also including an explicit "vectors are not element-aligned" specifier, such
  as "vE".
- Enhance the `v<size>:<abi>[:<pref>]` syntax to allow an 'e' for element in
  the `<abi>` and `<pref>` sections. This has two disadvantages:
  1. The logic for parsing vectors and scalars is shared, so we'd need to
     explicitly reject 'e' for scalars.
  2. We would need to specify this for every size of vector
- Allow `<size>` to be omitted in `v<size>:<abi>[:<pref>]`. In combination with
  the previous option, this could do what we need. The problem is that this
  doesn't really make sense otherwise, as setting all vectors to a fixed
  alignment isn't likely to be useful.

### Explicit alignment on all vectors

We could potentially avoid touching the Data Layout at all if we were to modify
the HLSL frontend to explicitly put an alignment on all vector types. This
nearly works but has a couple of problems:

1. Vectors can be created by compiler transformations, and these are outside of
   the scope of where the frontend could insert explicit alignment.
2. This ties the alignment to the frontend rather than the backends, forcing
   all targets of HLSL to use this alignment. This wouldn't necessarily make
   sense if we were targetting something other than DirectX or SPIR-V.

