---
title: "[0007] - Return Values of Loads, Samples, and Gathers"
params:
    status: Accepted
    authors:
        - bogner: Justin Bogner
---

## Introduction

In dxc a load, sample, or gather operation returns [a `%dx.types.ResRet`
value][ResRet], which is a structure containing four 32-bit values of a given
type and an `i32 status` that is used only for [CheckAccessFullyMapped].

When representing operations that will lower to these ones in LLVM IR, we need
to make some decisions about how the types will map.

[ResRet]: https://github.com/microsoft/DirectXShaderCompiler/blob/main/docs/DXIL.rst#resource-operation-return-types
[CheckAccessFullyMapped]: https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/checkaccessfullymapped

## Motivation

The LLVM intrinsics that map to specific DXIL operations aren't constrained to
fit in a stable binary format, so we have a fair amount of flexibility in how
we define them. We want them to be easy to work with both in the sense that
simple IR is more likely to optimize well and in the sense that we want it to
be easy to use and understand them in tests.

There are a couple of aspects of the [ResRet] types that are a bit awkward:
1. Operating on target specific named structs is unusual in LLVM IR.
2. DXIL shoehorns operations on doubles into using `ResRet.i32` and conversion
   functions.
3. [CheckAccessFullyMapped] is always present even when unused.

We'll tackle the types of the returned values first, and then discuss the check
bit slightly separately.

## Proposed solution

### Returning Values

TypedBuffer, CBuffer, and Texture loads, as well as samples and gathers, can
return 1 to 4 elements from the given resource, to a maximum of 16 bytes of
data. DXIL's modeling of this is influenced by DirectX and DXBC's history and
it generally treats these operations as returning 4 32-bit values. For 16-bit
elements the values are 16-bit values, and for 64-bit values the operations
return 4 32-bit integers and combine them with further operations.

In LLVM IR, the load intrinsics will return the contained type of the resource.
That is, for `Buffer<float>` this would return a single float, `Buffer<float4>`
would be a vector of 4 floats, `Buffer<double2>` a vector of two doubles, etc.

This makes lowering to DXIL operations more complicated than it would be if we
matched the return types more closely, but it simplifies the IR sufficiently to
be worthwhile.

### CheckAccessFullyMapped

Operations returning a bit just for the cases when [CheckAccessFullyMapped] is
used is kind of annoying. It's somewhat telling that some of the best
documentation of this function is [an article on sampler feedback that's
telling you how to replace that pattern][Sampler Feedback]. I think it's safe
to say usage of CheckAccessFullyMapped is rare in modern shaders, and we should
take an approach that makes code that doesn't use this operation easy to work
with.

To that end, we should provide two variants of any DXIL intrinsic that can
optionally return the check bit. The variants that do provide the bit can
simply return it as an `i1` that can be used directly rather than having to
pass an `i32` "status" to a separate operation, since there's only one thing
these are used for in practice.

Note that treating the return as an `i1` matches the undocumented behaviour of
`dxc`, which will implicitly add a `CheckAccessFullyMapped` operation to the IR
even if it wasn't present in HLSL source.

[Sampler Feedback]: https://devblogs.microsoft.com/directx/coming-to-directx-12-sampler-feedback-some-useful-once-hidden-data-unlocked/

### Examples

These are a few examples of what the LLVM intrinsics will look like and what
DXIL operations they'll lower to.

```llvm
  ; Load from a Buffer<float4>
  %val0 = call <4 x float> @llvm.dx.typedBufferLoad(
      target("dx.TypedBuffer", <4 x float>, 0, 0, 0) %buf0, i32 %ix)
  ; =>
  %val0 = call %dx.types.ResRet.f32 @dx.op.bufferLoad.f32(
      i32 68, %dx.types.Handle %buf0, i32 %ix, i32 undef)

  ; Load from a Buffer<float>
  %val1 = call float @llvm.dx.typedBufferLoad(
      target("dx.TypedBuffer", float, 0, 0, 0) %buf1, i32 %ix)
  ; =>
  %val1 = call %dx.types.ResRet.f32 @dx.op.bufferLoad.f32(
      i32 68, %dx.types.Handle %buf2, i32 %ix, i32 undef)
  ; Note: Only the 0th element of %val1 is valid

  ; Load from a Buffer<float4> followed by CheckAccessFullyMapped
  %agg2 = call {<4 x float>, i1} @llvm.dx.typedBufferLoad.checkbit(
      target("dx.TypedBuffer", <4 x float>, 0, 0, 0) %buf2, i32 %ix)
  %val2 = extractvalue {<4 x float>, i1} %agg2, 0
  %chk2 = extractvalue {<4 x float>, i1} %agg2, 1
  ; =>
  %val2 = call %dx.types.ResRet.f32 @dx.op.bufferLoad.f32(
      i32 68, %dx.types.Handle %buf2, i32 %ix, i32 undef)
  %bit2 = extractvalue %dx.types.ResRet.f32 %val2, 4
  %chk2 = call i1 @dx.op.CheckAccessFullyMapped.i32(i32 71, i32 %bit2)

  ; Load from a Buffer<int4>
  %val3 = call <4 x i32> @llvm.dx.typedBufferLoad(
      target("dx.TypedBuffer", <4 x i32>, 0, 0, 1) %buf3, i32 %ix)
  ; =>
  %val3 = call %dx.types.ResRet.i32 @dx.op.bufferLoad.i32(
      i32 68, %dx.types.Handle %buf3, i32 %ix, i32 undef)

  ; Load from a Buffer<double>
  %val4 = call double @llvm.dx.typedBufferLoad(
      target("dx.TypedBuffer", <4 x float>, 0, 0, 0) %buf4, i32 %ix)
  ; =>
  %res4 = call %dx.types.ResRet.i32 @dx.op.bufferLoad.i32(
      i32 68, %dx.types.Handle %buf4, i32 %ix, i32 undef)
  %lo4 = extractvalue %dx.types.ResRet.f32 %res4, 0
  %hi4 = extractvalue %dx.types.ResRet.f32 %res4, 1
  %val4 = call %dx.op.MakdeDouble.f64(i32 101, i32 %lo4, i32 %hi4)
```
