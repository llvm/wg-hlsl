<!-- {% raw %} -->

# Return Values of Loads, Samples, and Gathers

* Proposal: [0007](0007-the-resret-type.md)
* Author(s): [Justin Bogner](https://github.com/bogner)
* Status: **Accepted**
* PRs: llvm/llvm-project#104252

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
`dxc`, which will implicityly add a `CheckAccessFullyMapped` operation to the
IR even if it wasn't present in HLSL source.

[Sampler Feedback]: https://devblogs.microsoft.com/directx/coming-to-directx-12-sampler-feedback-some-useful-once-hidden-data-unlocked/

### Examples

These are a few examples of what the LLVM intrinsics will look like based on
the above.

```llvm
  ; Load from a Buffer<float4>
  %val0 = call <4 x float> @llvm.dx.typedBufferLoad(
              target("dx.TypedBuffer", <4 x float>, 0, 0, 0) %buf0, i32 %ix)

  ; Load from a Buffer<float>
  %val1 = call float @llvm.dx.typedBufferLoad(
              target("dx.TypedBuffer", float, 0, 0, 0) %buf1, i32 %ix)

  ; Load from a Buffer<float4> followed by CheckAccessFullyMapped
  %agg2 = call {<4 x float>, i1} @llvm.dx.typedBufferLoad.checkbit(
              target("dx.TypedBuffer", <4 x float>, 0, 0, 0) %buf0, i32 %ix)
  %val2 = extractvalue {<4 x float>, i1} %agg2, 0
  %chk2 = extractvalue {<4 x float>, i1} %agg2, 1
```

<!-- {% endraw %} -->
