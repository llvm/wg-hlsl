# DXIL Function Scalarization

* Proposal: [0009](0009-DXIL-Function-Scalarization.md)
* Author(s): [Farzon Lotfi](https://github.com/farzonl)
* Sponsor: [Farzon Lotfi](https://github.com/farzonl)
* Status: **Accepted**
* Impacted Projects: Clang

## Introduction

we need to be able to scalarize data structures, call instructions, and vector
operations like math ops, logical ops, bitcasts, loads, and stores. The goal of
this proposal is to present a solution for scalarizing vector operation and
call instructions via LLVM's pass manager. This proposal will not cover data
layout transformations.

## Motivation

Without Scalarizing the data structures and call instructions we can't generate
valid DXIL.

## Background

In DXC, Scalarization and SROA are merged in unfortunate ways. Most of that
code can be found here: [`SROA_Parameter_HLSL` Module pass in `ScalarReplAggregatesHLSL.cpp`](https://github.com/microsoft/DirectXShaderCompiler/blob/main/lib/Transforms/Scalar/ScalarReplAggregatesHLSL.cpp#L4263).
The specific instructions DXC operates on are `CallInst`, `LoadInst`,
`StoreInst`, `GetElementPtrInst`, `AddrSpaceCastInst`, `BitCastInst`, and
`MemIntrinsic`. DXC works on two sets of data globals and function arguments
Not covered in this proposal is the handling of  global data. That will be
addressed in a later proposal. Also not covered are ops typically covered by
SROA like `Allocas` as that should be handled via an O1 optimization pipeline.

## Proposal

Our goal should be to emit legal DXIL with behavioral similarity to DXC. To
that end it makes the most sense to use the Scalarizer pass.

* [Scalarizer.cpp](https://github.com/llvm/llvm-project/blob/main/llvm/lib/Transforms/Scalar/Scalarizer.cpp)

The `Scalarizer` pass is a `FunctionPass`. The pass does not solve all our
requirements. For example, it won't transform vectors into a DXIL legal Scalar
form. This is mostly of concern for data structures defined globally.
The `scalarizer` pass has two flags relevant to our use case:

* `-scalarize-load-store`
* `-scalarize-variable-insert-extract`.

These flags will handle the `BitCastInst`, `CallInst`, `LoadInst` and
`StoreInst`, and `GetElementPtrInst` cases.

The `AddrSpaceCastInst` case is unique to DXC. DXC was using `AddrSpaceCastInst`
to fix up bad codgen to avoid undefined behavior or generating illegal DXIL.
Any remaining `AddrSpaceCastInst` should be handled by the O1 optimization
pipeline.

`MemIntrinsic` is the odd case out. Clang does not currently emit memcpy for
the same cases as DXC. Further, DXC's emits of `memcpy`, `memset`, and `memmove`
aren't something that will be carried forward because clang will do
scalarization late and DXC did it early. What that means in practice is there
won't be any `MemIntrinsic` transformations we can depend on via the
optimization pipeline.

In DXC operations like memcpy and memset most easily happen in global scope.
In my observation these cases get converted into cbuffer. Since we don't have
cbuffer support yet we can likely hold off on this case. Further, a future
Data Scalarization Proposal will iterate other cbuffer cases that can lay
the ground work for supporting `MemIntrinsic`.

The team debated how early or late this pass should run and considered three
ways to onboard this pass. There was also a discussion on how the scalarizer
passes only works on llvm intrinsics and how we would extend it for DirectX
Intrinsics.

### Proposal: When to run pass

The team determined it was best for this pass to run in the DirectX backend.
That allows The DirectX backend to be agnostic to the frontend.
The team also determined the pass should run as late as possible. This has two
benefits. First, code size: if scalarization happens too early then things like
the `-combiner-alias-analysis` pass limits are reached. For this particular
pass and potentially others if the limits are reached it does not perform a
transformation. That means there is the potential for less efficient code
generation if we scalarize to soon as some optimizations that benefit from
less IR wont run. Second, scalarization for DXIL should be considered a
legalization step. To that end it should happen at or right before
`DXILOpLowering`.

`DXILOpLowering` is also the last place for a functional reason. The scalarizer
pass only operates on llvm intrinsics that are `TriviallyVectorizable`. Further
it only converts the scalarized llvm intrinsics meaning there is no way for it
to know about DXIL OPs.

### Proposal: Ways to add the Scalarizer pass

The Scalarizer pass has been converted to the new pass manager (new PM). That
is a problem for us because the new PM is only experimental in the backend.
The Direct X backend is still on the legacy PM. Further, new PM isn't
hooked up in clang yet via `BackendUtil.cpp`'s `AddEmitPasses`.

There are a few ways we could go about this:

1. support `PassInfoMixin` in the DirectX backend.
   * Need to override "buildCodeGenPipeline" for the DirectX backend.
   * Pro: implementation is easy enough: https://github.com/llvm/llvm-project/compare/main...farzonl:llvm-project:create-codegen-pass-builder
   * Con: Need to hooked up new PM in clang via `BackendUtil.cpp`'s
     `AddEmitPasses`. the `TM->addPassesToEmitFile` is all legacy PM.
2. Add the Legacy pass manager abstraction for `scalarizer` back
   * We would be undoing the work the community did to port this pass.
   * Pro: works seamlessly: https://github.com/llvm/llvm-project/pull/107427
3. Fork the `scalarizer` so we can have a legacy and `PassInfoMixin` in the
   DirectX Backend?
   * We could make this work for DXIL ops and not just intrinsics.
   * Con: Maintaining passes like this defeats some of the benefits of the
     modernization effort.

The team decided the best path forward was to add the legacy pass manager back.
The initial reaction of the LLVM community is that this is fine.

### Proposal: Add Support for DirectX intrinsics

`isTriviallyScalariable(Intrinsic::ID ID)` will be renamed to `isTriviallyScalarizable`.
We will add a Module parameter so that we can lookup `M.getTargetTriple();`.
We will then have a condition on `Triple::ArchType ==  == Triple::dxil` that
will call a static function with all the DirectX intrinsics that need to be
scalarized specified.
