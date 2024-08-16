# DXIL Scalarization

* Proposal: [NNNN](NNNN-DXIL-Scalarization.md)
* Author(s): [Farzon Lotfi](https://github.com/farzonl)
* Sponsor: [Farzon Lotfi](https://github.com/farzonl)
* Status: **Under Consideration**
* Impacted Projects: Clang

## Introduction
As mentioned in [DXIL.rst](https://github.com/microsoft/DirectXShaderCompiler/blob/main/docs/DXIL.rst#vectors) 
"HLSL vectors are scalarized" and "Matrices are lowered to vectors". Therefore,
 we need to be able to scalarize datastructures, call instructions, and vector 
 operations like mathamatical, logical and bitcasts. The goal of this proposal 
 is to present a solution for LLVM's pass manager.

## Motivation
Without Scalarizing the data structures and call instructions we can't generate
 valid DXIL.

 ## Background
 In DXC Scalarization and SROA are merged in unfortnate ways. Most of that code
 can be found here: [`SROA_Parameter_HLSL` Module pass in `ScalarReplAggregatesHLSL.cpp`](https://github.com/microsoft/DirectXShaderCompiler/blob/main/lib/Transforms/Scalar/ScalarReplAggregatesHLSL.cpp#L4263). 
The specific instructions DXC operates on are `CallInst`, `LoadInst`, 
`StoreInst`, `GetElementPtrInst`, `AddrSpaceCastInst`, `BitCastInst`, and 
`MemIntrinsic`. Not covered in this proposal is the handling of `Allocas`.
That will be addressed in a later proposal covering DXIL Legalization.

## Proposal
Our goal should be legal DIXL with behavioral similarity to DXC. To that end it
 makes the most sense to use the Scalarizer pass.
- [Scalarizer.cpp](https://github.com/llvm/llvm-project/blob/main/llvm/lib/Transforms/Scalar/Scalarizer.cpp)

The `scalarizer` pass with the `-scalarize-load-store` and 
`-scalarize-variable-insert-extract` flags  will handle the `BitCastInst`, 
`CallInst`, `LoadInst` and `StoreInst`, and `GetElementPtrInst` cases. The 
`AddrSpaceCastInst` case isn't relevant for upstream LLVM.

`MemIntrinsic` is the odd case out. We don't currently emit memcpy for
the same cases we do in DXC.
In many cases operations like memcpy and memset seem to happen in global scope.
See Example:
- https://hlsl.godbolt.org/z/8vx1Yee7b

In my observation these cases get converted into cbuffer. Since we don't have
cbuffer support yet we can likely hold off on this cases.


The team debated when how early or late this pass should run and three ways to 
onboard this pass. There was also a discussion on  the scalarizer passes only 
working on llvm intrinsics and how to allow for DirectX Intrinsics.

### Proposal: When to run pass
The team determined it was best for this pass to run in the DirectX backend.
That allows The DirectX backend to be agnostic to the frontend.
The team also determined the pass should run as late as possible. This has two
benefits. First code size. if scalarization happens too early things like the 
`-combiner-alias-analysis` pass limits are reached. More optimizations will be
possible as analysis passes will benefit from less IR. Second, scalarization 
for DXIL should be considered a legalization step. To that end it should happen
at or right before `DXILOpLowering`.

`DXILOpLowering` is also the last place for a functional reason. The scalarizer
pass only operates on llvm intrinsics that are `TriviallyVectorizable`. Further
it only converts the scalarized llvm intrinsics meaning there is no way for it
to know abot DXIL OPs.

### Proposal: Ways to add the Scalarizer Pass
There are a few ways we could go about this:
1. support `PassInfoMixin` in the DirectX backend. 
   - Need to override "buildCodeGenPipeline" for the DirectX backend.
   - Pro: implementation is easy enough: https://github.com/llvm/llvm-project/compare/main...farzonl:llvm-project:create-codegen-pass-builder
   - Con: The new PM isn't hooked up in clang yet via `BackendUtil.cpp`'s
     `AddEmitPasses`. the `TM->addPassesToEmitFile` is all legacy PM.
2. Add the Legacy Pass manager abstraction for `scalarizer` back
   - We would be undoing the work the community did to port this pass.
   - Pro: works seemlessly: https://github.com/llvm/llvm-project/compare/main...farzonl:llvm-project:add-legacy-scalarizer-for-dxil
3. Fork the `scalarizer` so we can have a legacy and `PassInfoMixin` in the 
   DirectX Backend?
   - We could make this work for dxil ops and not just intrinsics.
   - Con: Mantaining passes like this defeats some of the benefits of the
     modernization effort.

The team decided the best path forward was to add the legacy pass manager back.

### Proposal: Add Support for DirectX intrinsics
`isTriviallyScalariable(Intrinsic::ID ID)` will be renamed to `isTriviallyScalarizable`.
We will add a Module parameter so that we can lookup `M.getTargetTriple();`. 
We will then have a condition on `Triple::ArchType ==  == Triple::dxil` that 
will call a static function with all the DirectX intrinsics that need to be
scalarized specified.
