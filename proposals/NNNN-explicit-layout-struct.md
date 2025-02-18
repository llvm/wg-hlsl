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

packoffset that only specifies the first field:
> note: This emits a warning in DXC. Do we really want to support it?

```llvm
; cbuffer packoffset1 {
;   float x : packoffset(c1.x);
;   float y;
; };
target("dx.Layout", { i32, i32 }, 24, 16, 20)
```

packoffset that only specifies a later field:
> note: This behaves differently between DXIL and SPIR-V in DXC, and the DXIL
> behaviour is very surprising. Do we want to allow this?

```llvm
; cbuffer packoffset1 {
;   float x;
;   float y : packoffset(c1.x);
; };
target("dx.Layout", { i32, i32 }, 24, 20, 16)
target("spirv.Layout", { i32, i32 }, 20, 0, 16)
```

packoffset that reorders fields:
> note: This fails to compile for SPIR-V in DXC. Is this worth handling?

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

- Should we also add a `target("dx.CBufArray", <type>, <size>)` type, rather
  than having the CBuffer logic need to be aware of special array element
  spacing rules?
- Should reordering fields actually be allowed here?

## Acknowledgments

This proposal is expanded from comments in [llvm/wg-hlsl#94] and follow up
conversations.

[llvm/wg-hlsl#94]: https://github.com/llvm/wg-hlsl/pull/94

<!-- {% endraw %} -->
