<!-- {% raw %} -->

# Types with explicit layouts in DXIL and SPIR-V

* Proposal: [NNNN](NNNN-explicit-layout-struct.md)
* Author(s): [bogner](https://github.com/bogner)
* Status: **Design In Progress**

## Introduction

This introduces the `dx.Layout` and `spirv.Layout` target extension types,
which can be used to represent HLSL structures that need explicit layout
information in LLVM IR.

## Motivation

Some HLSL types have layout that isn't practical to derive from the module's
DataLayout. This includes all kinds of `cbuffer`, but especially those that use
`packoffset`, and also applies to structs that use the vulkan `[[vk::offset()]]
extension and possibly objects with specific alignment specified on subobjects.

We need to be able to represent these types in IR so that we can generate
correct code in the backends.

## Proposed solution

We should implement a target type that includes a struct type, total size, and
offsets for each member of the struct. This type can then be used in other
target types, such as CBuffer or StructuredBuffer definitions, or even in other
layout types. We need target types for DirectX and for SPIR-V, but the types
can and should mirror each other.

```
target("[dx|spirv].Layout", %struct_type, <size>, [offset...])
```

### Examples

In the examples below we generally use "dx.Layout", since the "spirv.Layout"
variants would be identical.

While these aren't necessarily needed for types that don't have explicit layout
rules, some examples of "standard" layout objects represented this way are
helpful:

```llvm
; struct simple1 {
;   float x;
;   float y;
; };
%__hlsl_simple1 = { i32, i32 }
target("dx.Layout", %__hlsl_simple1, 8, 0, 4)

; struct simple2 {
;   float3 x;
;   float y;
; };
%__hlsl_simple2 = { <3 x float>, float }
target("dx.Layout", %__hlsl_simple2, 16, 0, 12)

; struct nested {
;   simple2 s2;
;   simple1 s1;
; };
%__hlsl_nested = type { target("dx.Layout", %__hlsl_simple2, 16, 0, 12),
                        target("dx.Layout", %__hlsl_simple1, 8, 0, 4) }
target("dx.Layout", %__layout_nested, 24, 0, 16)
```

Objects whose layout differs in cbuffers than in structs:

```llvm
; struct array_struct {
;   float x[4];
;   float y;
; };
%__hlsl_array_struct = type { [4 x float], float }
target("dx.Layout", %__hlsl_array_struct, 20, 0, 16)

; cbuffer array_cbuf1 {
;   float x[4];
;   float y;
; };
target("dx.Layout", %__hlsl_array_struct, 56, 0, 52)

; cbuffer array_cbuf2 {
;   array_struct s;
; };
target("dx.Layout", %__hlsl_array_struct, 56, 0, 52)

; struct nested2 {
;   simple1 s1;
;   simple2 s2;
; };
%__hlsl_nested2 = type { target("dx.Layout", %__hlsl_simple1, 8, 0, 4),
                         target("dx.Layout", %__hlsl_simple2, 16, 0, 12) }
target("dx.Layout", %__hlsl_nested2, 24, 0, 8)

; cbuffer nested_cbuf {
;   simple1 s1;
;   simple2 s2;
; };
target("dx.Layout", %__hlsl_nested2, 32, 0, 16)
```

Simple usage of packoffset:

```llvm
; cbuffer packoffset1 {
;   float x : packoffset(c1.x);
;   float y : packoffset(c2.y);
; };
target("dx.Layout", { i32, i32 }, 40, 16, 36)
```

packoffset that reorders fields:
> note: This does not currently work in DXC targeting SPIR-V.

```llvm
; cbuffer packoffset1 {
;   float x : packoffset(c2.y);
;   float y : packoffset(c1.x);
; };
target("dx.Layout", { i32, i32 }, 40, 36, 16)
```

Use of `[[vk::offset()]]`:

```llvm
; struct vkoffset1 {
;   float2 a;
;   [[vk::offset(8)]] float2 b;
; }
%__hlsl_vkoffset1 = { <2 x float>, <2 x float> }
target("spirv.Layout", %__hlsl_vkoffset1, 12, 0, 8)

; struct complex {
; float r;
; float i;
; };
; struct vkoffset2 {
;   float2 a;
;   [[vk::offset(8) complex b;
; }
%__hlsl_vkoffset2 = { <2 x float>, { float, float } }
target("spirv.Layout", %__hlsl_vkoffset1, 16, 0, 8)
```

## Open questions

#### Arrays in CBuffers

Should we also add a `target("dx.CBufArray", <type>, <size>)` type, rather than
having the CBuffer logic need to be aware of special array element spacing
rules?

#### Decaying to non-target types

Operations like `resource.getpointer` can expose us to the contained type of a
resource, but should that give us an object of the underlying struct or the
target type? For the former, we would lose the layout, which is problematic.
For the latter, we need to talk about GEPs.

If we can have pointers of the target type, we'd either need to teach GEP to
handle these, which is a fairly wide-reaching change, or we would need a set of
GEP-like intrinsics.

This will need to be resolved in order to use these in StructuredBuffer and for
most real use-cases of `vk::offset`.

#### Copying in and out of the layout

How do we convert from the Layout types to types without the offsets? We'll
probably need an intrinsic that does a logical copy from the target type to a
compatible structure. See https://godbolt.org/z/rh5dvd3E7 for an example.

#### Struct layouts in Clang

Clang uses [ASTContext::getRecordLayout] to get the offset of a member when
needed. This proposal means that we will not update this class to be aware of
`vk::offset` and `packedoffset`. The goal of this proposal is to avoid adding
explicit padding members in the llvm:StructType as is done when handling
`alignof` in C++.

[ASTContext::getRecordLayout]: https://github.com/llvm/llvm-project/blob/aa9e519b2423/clang/lib/AST/RecordLayoutBuilder.cpp#L3321

If we update `ASTContext::getRecordLayout`, then the explicit padding will be
added to the llvm::StructType. If we do not update it, then we will have to
consider every spot in Clang that calls it to see if we need to special case
the HLSL layout.

Currently known issue are: `offsetof` and `sizeof`. There is a lot more that
needs to be looked into in Clang. `ASTRecordLayout` is passed around to a lot
of functions, without the original type.

## Alternative Solutions

There are a few other approaches we might take here in order to get a handle on
the many open questions:

- Target types that describe the bit layout (padding included), with
  integer fields to describe the logical layout
- Target types that describe the bit layout with fields to describe padding
- Adding or modifying a first class structure type with layout information
- Adding explicit padding types to LLVM's type system
- Accessors to the layout types that give us a "physical layout" struct of the
  object.

It's clear that the layout type is sufficient for cbuffers, but it has some
problems when trying to use it more generically. We need to investigate further
if a combined solution for cbuffers, vk::offset, and alignas is feasible.

## Acknowledgments

This proposal is expanded from comments in [llvm/wg-hlsl#94] and follow up
conversations.

[llvm/wg-hlsl#94]: https://github.com/llvm/wg-hlsl/pull/94

<!-- {% endraw %} -->
