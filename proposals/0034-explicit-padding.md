---
title: "[0034] - Explicit Padding in Structs and CBuffer Arrays"
params:
    status: Accepted
    authors:
        - bogner: Justin Bogner
---


## Introduction

We introduce an explicit padding type for HLSL, and construct cbuffers using
this type to unambiguously represent their layout. This will be used for layout
rules implicit to cbuffers (such as struct and array alignment and element
size) as well as for `packoffset` annotations in cbuffers and `vk::offset`
annotations outside of cbuffers.

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

The padding type will be a target type with a parameter for the size in bytes.
For DirectX, this would look like `target("dx.Layout", 4)` for 4 bytes of
padding. For SPIR-V, `target("spirv.Padding", 8)` for 8 bytes of padding. We
may attempt to come up with a first-class type in LLVM for these purposes in
the future.

### Implicit layout rules in a cbuffer

CBuffers in HLSL have very specific layout rules. Scalars and vectors follow
the HLSL/DirectX alignment rules and are aligned as per their scalar size.
Structs and arrays are always aligned on a 16-byte boundary, regardless of
their contents. Furthermore, array elements are each aligned on a 16-byte
boundary.

Since we can't really represent these rules by simply forcing alignments, we
instead use explicit padding between elements to enforce that all arrays and
structs start on 16 byte boundary.

We then emulate the array padding with an array of objects that consist of a
struct containing the element type and padding to 16 bytes, followed by a
single instance of the element type itself. See [CBuffer Padded arrays at the
HLSL-level] for details.

[CBuffer Padded arrays at the HLSL-level]: #cbuffer-padded-arrays-at-the-hlsl-level

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

For structs, we add padding to align them as appropriate:

```hlsl
struct S {
  int v;
};
cbuffer cb1 : register(b0) {
  int i; // offset   0,  size 4  (+12)
  S s;   // offset  16,  size 4
  int j; // offset  20,  size 4
}

```llvm
%__cblayout_cb1 = type <{
  i32, target("dx.Padding", 12),
  i32,
  i32
}>
```

For arrays, we'll have padding within elements to fill to a 16-byte boundary,
and padding before arrays in order for them to start at 16-byte boundaries.
Consider `cb1`:

```hlsl
cbuffer cb2 : register(b0) {
  float a1[3];        // offset   0,  size 4  (+12) * 3
  double3 a2[2];      // offset   48, size 24  (+8) * 2
  uint4 a3[2];        // offset  112, size 16       * 2
  float16_t a4[2][2]; // offset  144, size  2 (+14) * 4
}
```

```llvm
%__cblayout_cb2 = type <{
  <{ [2 x <{ float, target("dx.Padding", 12) }>], float }>,
  target("dx.Padding", 12"),
  <{ [1 x <{ <3 x double>, target("dx.Padding", 8) }>], <3 x double> }>,
  target("dx.Padding", 8),
  [ 2 x <4 x i32> ],
  <{ [3 x <{ half, target("dx.Padding", 14) }>], half }>
}>
```

[__cblayout]: https://github.com/llvm/wg-hlsl/blob/4570a9cfc5c4b1e5bc0b773a6fb7b22014ac6d3b/proposals/0016-constant-buffers.md#lowering-constant-buffer-resources-to-llvm-ir "Lowering Constant Buffer Resources to LLVM IR"

### CBuffer Padded arrays at the HLSL-level

Arrays in cbuffers need padding between elements if the element size is not a
multiple of 16 bytes. However, we can ignore this at the AST level as the
padding is invisible to all operations representable in HLSL. We already mark
objects in cbuffers via an address space, so nothing needs to change here.

In clang codegen we'll need to recognize that a type is in a cbuffer and
generate struct and array accesses appropriately. By keying off of the address
space, we can ensure that when we lower accesses to LLVM IR we are able to do
so using the padded type logic.

When an object is copied from an object with a cbuffer layout to one with a
standard layout, this goes through codegen logic to emit aggregate copies in
clang. Here we can recognize that the source of the copy is in the cbuffer
address space and break the copy up into elementwise pieces.

## Alternatives considered

See [llvm-project/wg-hlsl#171] for the previous attempt at representing these
types.

Regarding the padding type, we considered the following options:

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
  
We settled on a target type with a size parameter for now.

[llvm-project/wg-hlsl#171]: https://github.com/llvm/wg-hlsl/pull/171

