<!-- {% raw %} -->

# Explicit Padding in Structs and CBuffer Arrays

* Proposal: [NNNN](NNNN-explicit-padding.md)
* Author(s): [Justin Bogner](https://github.com/bogner)
* Status: **Design In Progress**

## Introduction

We introduce an explicit padding type for HLSL, and construct cbuffer arrays
and structs that are annotated with `packoffset` or `vk::offset` using this
type to unambiguously lay out these objects.

## Motivation

HLSL has a few contexts where we have types with a layout that doesn't match
the usual rules that follow from C++ definitions and targets' data layouts. We
can generally describe the appropriate type representations for these using
explicit padding, but some care needs to be taken:

- Arrays in CBuffers may have padding in between members, but crucially they do
  not have padding after the last member. This needs special handling to
  represent.

- There are two HLSL constructs that may introduce arbitrary padding to a
  struct. In a cbuffer, the `packoffset` attribute specifies the offset of a
  member, and outside of cbuffers, the `vk::offset` vulkan attribute may do the
  same.

- Simply padding structures with `i8` as is typical with ABI-related padding
  makes it difficult to recover which struct elements are padding vs which are
  subobjects. This matters in some backends, and is specifically important for
  SPIR-V where we need to map a logical indices into the struct into physical
  offsets.

## Proposed solution

Introduce an explicit padding type and use this type for the padding in the
various constructs that need it.

The padding type will be defined as one of the following:

- A first class LLVM type called `pad8`, which is equivalent but distinct from
  `i8`. This would need an RFC to the wider LLVM community and would need to be
  useful in other contexts (such as ABI-mandated padding).
- A well-known named type `%pad8`, defined as a named struct containing a
  single `i8`. This is the simplest option but requires backends that are
  interested in this type to participate in a secret handshake.
- Target types such as `target("dx.pad8")` and `target("spirv.pad8")`. This is
  somewhat awkward because the type isn't really tied to a target, but target
  types need to be. Targets that don't need to differentiate between padding
  and actual members could simply use `i8`.

> TODO: Choose one of these three options and move the others to the
> "alternatives" section.

### Structs with annotations

Generally speaking HLSL structs are equivalent to packed structs in C++. We can
simply add padding between members as appropriate in order to satisfy the rules
specified by `packoffset`, `vk::offset`, or otherwise by HLSL semantics.

There is one complicating factor here. Both `dxc` and `fxc` allow `packoffset`
to be used to layout a struct in an order that does not match the
lexicographical order:

```hlsl
cbuffer cb0 {
    int x : packoffset(c0.y);
    float y : packoffset(c0.x);
}
```

To support this, we need to create the underlying LLVM type in the order that
matches the packoffsets rather than the order as written, so we would end up
with `{ float, i32 }` here, losing the lexicographical order. This is probably
okay since we need to create artificial types for cbuffers anyway (such as when
we filter out resource types that are declared within the cbuffer), but may not
make for a particularly good debugging experience.

### Arrays in a cbuffer

CBuffers in HLSL have very specific layout rules. Each "object" starts at a
16-byte boundary, which is mostly explainable as a 16-byte alignment
requirement, but applies to array elements rather than the array itself in a
way that doesn't match the general language. We can emulate this with an array
of objects that consist of a struct containing the element type and padding to
16 bytes, followed by a single instance of the element type itself. See
[CBuffer Padded arrays at the HLSL-level] for details.

[CBuffer Padded arrays at the HLSL-level]: #cbuffer-padded-arrays-at-the-hlsl-level

## Detailed design

### CBuffer representation at the LLVM level

CBuffers will continue to use a [__cblayout] type, but will no longer use a
`target("dx.Layout", ...)` type. 

When using `packoffset`, we'll add explicit padding as necessary. Consider
`cb0`:

```hlsl
cbuffer cb0 : register(b0) {
  int x : packoffset(c0.y);
  float y : packoffset(c1.z);
}
```

```llvm
%__cblayout_cb0 = type <{
  [4 x %pad8],
  i32,
  [16 x %pad8],
  float
}>
```

For arrays, we'll have padding within elements to fill to a 16-byte boundary,
and padding before arrays in order for them to start at 16-byte boundaries.
Consider `cb1`:

```hlsl
cbuffer cb1 : register(b0) {
  float a1[3];        // offset   0,  size 4  (+12) * 3
  double3 a2[2];      // offset   48, size 24  (+8) * 2
  uint4 a3[2];        // offset  112, size 16       * 2
  float16_t a4[2][2]; // offset  144, size  2 (+14) * 4
}
```

```llvm
%__cblayout_cb1 = type <{
  <{ [2 x <{ float, [12 x %pad8] }>], float }>, [12 x %pad8],
  <{ [1 x <{ <3 x double>, [8 x %pad8] }>], <3 x double> }>, [8 x %pad8],
  [ 2 x <4 x i32> ],
  <{ [3 x <{ half, [14 x %pad8] }>], half }>
}>
```

[__cblayout]: https://github.com/llvm/wg-hlsl/blob/4570a9cfc5c4b1e5bc0b773a6fb7b22014ac6d3b/proposals/0016-constant-buffers.md#lowering-constant-buffer-resources-to-llvm-ir "Lowering Constant Buffer Resources to LLVM IR"

### CBuffer Padded arrays at the HLSL-level

Arrays in cbuffers need padding between elements if the element size is not a
multiple of 16 bytes. This can be implemented as if these were objects of a C++
type like the following rather than simple arrays:

```c++
#include <cstdint>
#include <type_traits>

using pad8_t = uint8_t;

template <typename T, std::size_t N, bool NeedsPadding = sizeof(T) % 16 != 0>
struct CBufArray;

template <typename T, std::size_t N> struct CBufArray<T, N, true> {
  struct PaddedT {
    T Element;
    uint8_t Padding[16 - (sizeof(T) % 16)];
  };
  PaddedT Elems[N - 1];
  T LastElem;

  const T &operator[](std::size_t I) const {
    return I == N - 1 ? LastElem : Elems[I].Element;
  }
};

template <typename T, std::size_t N> struct CBufArray<T, N, false> {
  T Elems[N];

  const T &operator[](std::size_t I) const { return Elems[I]; }
};
```

We won't actually implement this type in HLSL, but we do need to model arrays
in cbuffers equivalently to this in the clang ASTs. This has to be done in the
AST and not later during clang codegen because offsets into arrays are
calculated in various places based off of the AST types.

## Alternatives considered

See [llvm-project/wg-hlsl#171] for the previous attempt at representing these
types.

[llvm-project/wg-hlsl#171]: https://github.com/llvm/wg-hlsl/pull/171

<!-- {% endraw %} -->
