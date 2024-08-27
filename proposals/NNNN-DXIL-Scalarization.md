# DXIL Scalarization

* Proposal: [NNNN](NNNN-DXIL-Scalarization.md)
* Author(s): [Farzon Lotfi](https://github.com/farzonl)
* Sponsor: [Farzon Lotfi](https://github.com/farzonl)
* Status: **Under Consideration**
* Impacted Projects: Clang

## Introduction
As mentioned in [DXIL.rst](https://github.com/microsoft/DirectXShaderCompiler/blob/main/docs/DXIL.rst#vectors) 
"HLSL vectors are scalarized" and "Matrices are lowered to vectors". Therefore,
 we need to be able to scalarize these types in clang DirectX backend. In DXC, 
 this is done via [`SROA_Parameter_HLSL` Module pass in `ScalarReplAggregatesHLSL.cpp`](https://github.com/microsoft/DirectXShaderCompiler/blob/main/lib/Transforms/Scalar/ScalarReplAggregatesHLSL.cpp#L4263). 
 The goal of this proposal is the present a solution for LLVM's pass manager.

## Motivation
Without Scalarizing the data structures and call instructions we can't generate valid DXIL.

 ## Background
The rewrite functions specified in the appendix cover the behavior we need to 
support for scalarization. The specific instructions DXC operates on are
`CallInst`, `LoadInst`, `StoreInst`, `GetElementPtrInst`, `AddrSpaceCastInst`, `BitCastInst`,
and `MemIntrinsic`. DXC  works on two sets of data globals\allocas and 
function arguments via the `RewriteForScalarRepl`.

There are a few ways we could tackle this work that gets us towards behavioral parity.
A good example is to look at:
- [SPIRVEmitIntrinsics.cpp](https://github.com/llvm/llvm-project/blob/main/llvm/lib/Target/SPIRV/SPIRVEmitIntrinsics.cpp)
- [SROA.cpp](https://github.com/llvm/llvm-project/blob/main/llvm/lib/Transforms/Scalar/SROA.cpp)
- [Scalarizer.cpp](https://github.com/llvm/llvm-project/blob/main/llvm/lib/Transforms/Scalar/Scalarizer.cpp)

Given how the above passes are written `GetElementPtrInst`, `AddrSpaceCastInst`,
`BitCastInst`, `CallInst`, `LoadInst` and `StoreInst` should be handled.
`BitCastInst` might have some translational work needed so we can convert 
`bitcast` to something like `sitofp`.

`MemIntrinsic` is the odd case out. We don't currently emit memcpy for
the same cases we do in DXC and llvm's SROA doesn't emit memcpys at all.
A good pass to look at that might give insperation here is:
`llvm\lib\Transforms\Scalar\ScalarizeMaskedMemIntrin.cpp`.

There likely shouldn't be any need for `AddrSpaceCastInst`. Further if a new pass is needed following the `visitGetElementPtrInst`, `visitBitCastInst`,  `visitMemSetInst`, & `visitMemTransferInst` should give us the coverage we need.

### Allocas and what SROA can do for us
```llvm
define void @test(i7 %x) {
bb:
  %res = alloca [2 x i8]
  %tmp = alloca { i1, i3 }
  %tmp.1 = getelementptr i8, ptr %tmp, i64 1
  store i7 %x, ptr %tmp.1
  call void @llvm.memcpy.p0.p0.i64(ptr %res, ptr %tmp, i64 2, i1 false)
  call i8 @use(ptr %res)
  ret void
}
```
Notice temps Allocas split in two and memcpy of temp to res is also split.
Additionally alignment is denoted.
```llvm
define void @test(i7 %x) {
bb:
  %res = alloca [2 x i8], align 1
  %tmp.sroa.0 = alloca i1, align 8
  %tmp.sroa.1 = alloca i3, align 1
  store i7 %x, ptr %tmp.sroa.1, align 1
  call void @llvm.memcpy.p0.p0.i64(ptr align 1 %res, ptr align 8 %tmp.sroa.0, i64 1, i1 false)
  %tmp.sroa.1.0.res.sroa_idx = getelementptr inbounds i8, ptr %res, i64 1
  call void @llvm.memcpy.p0.p0.i64(ptr align 1 %tmp.sroa.1.0.res.sroa_idx, ptr align 1 %tmp.sroa.1, i64 1, i1 false)
  %0 = call i8 @use(ptr %res)
  ret void
}

```
This behavior isn't particularly useful to HLSL. What we want is
something closer to this godbolt example:
https://hlsl.godbolt.org/z/h9xPoE6T1

in our example we see DXC
replace 
%5 = alloca <4 x float>, align 4
store <4 x float> %a, <4 x float>* %5, align 4

We can acomplish the same thing like so:

```llvm
define  <4 x float>  @test( <4 x float> %x) {
bb:
  %res = alloca <4 x float>
  store <4 x float> %x, <4 x float>* %res
  %val = load <4 x float>, ptr %res
  ret <4 x float> %val
}
```
Notice how the alloca is gone after running SROA
```llvm
define <4 x float> @test(<4 x float> %x) {
bb:
  ret <4 x float> %x
}
```

### Mem intrinsics
In many cases operations like memcpy and memset seem to happen in global scope.
In my observation these cases get converted into cbuffer. Since we don't have
cbuffer support yet we can likely hold off on this cases.
### Example
https://hlsl.godbolt.org/z/8vx1Yee7b

### Loads & Stores
We also will get `LoadInst` and `StoreInst` for non DXIL resources  via  `visitLoadInst` and `visitStoreInst`.

From experimentation I'd like to use the `Scalarizer` pass for this. The problem is that pass is a `PassInfoMixin`
while the rest of our backend passes use the Legacy Pass manager. Maybe we could write a legacy Frontend for it?

#### Store example
https://hlsl.godbolt.org/z/sE7Edvs9n
```c++
groupshared float3 sharedData[2];
export void fn2() {
    sharedData[0] = float3(1.0f, 2.0f, 3.0f);
    sharedData[1] = float3(2.0f, 4.0f, 6.0f);
}
```
```powershell
<path>\bin\clang.exe -T lib_6_8 .\llvm\test\CodeGen\DirectX\store.hlsl
```
```llvm
@"?sharedData@@3PAT?$__vector@M$02@__clang@@A" = local_unnamed_addr addrspace(3) global [2 x <3 x float>] zeroinitializer, align 16

define void @"?fn2@@YAXXZ"() local_unnamed_addr {
  store <3 x float> <float 1.000000e+00, float 2.000000e+00, float 3.000000e+00>, ptr addrspace(3) @"?sharedData@@3PAT?$__vector@M$02@__clang@@A", align 16
  store <3 x float> <float 2.000000e+00, float 4.000000e+00, float 6.000000e+00>, ptr addrspace(3) getelementptr inbounds (i8, ptr addrspace(3) @"?sharedData@@3PAT?$__vector@M$02@__clang@@A", i32 16), align 16
  ret void
}
```
```powershell
<path>\bin\opt.exe -S -passes=scalarizer -scalarize-load-store .\llvm\test\CodeGen\DirectX\scalarize2.ll
```
```llvm
@"?sharedData@@3PAT?$__vector@M$02@__clang@@A" = local_unnamed_addr addrspace(3) global [2 x <3 x float>] zeroinitializer, align 16

define void @"?fn2@@YAXXZ"() local_unnamed_addr {
  store float 1.000000e+00, ptr addrspace(3) @"?sharedData@@3PAT?$__vector@M$02@__clang@@A", align 16
  store float 2.000000e+00, ptr addrspace(3) getelementptr (float, ptr addrspace(3) @"?sharedData@@3PAT?$__vector@M$02@__clang@@A", i32 1), align 4
  store float 3.000000e+00, ptr addrspace(3) getelementptr (float, ptr addrspace(3) @"?sharedData@@3PAT?$__vector@M$02@__clang@@A", i32 2), align 8
  store float 2.000000e+00, ptr addrspace(3) getelementptr inbounds (i8, ptr addrspace(3) @"?sharedData@@3PAT?$__vector@M$02@__clang@@A", i32 16), align 16
  store float 4.000000e+00, ptr addrspace(3) getelementptr (float, ptr addrspace(3) getelementptr inbounds (i8, ptr addrspace(3) @"?sharedData@@3PAT?$__vector@M$02@__clang@@A", i32 16), i32 1), align 4       
  store float 6.000000e+00, ptr addrspace(3) getelementptr (float, ptr addrspace(3) getelementptr inbounds (i8, ptr addrspace(3) @"?sharedData@@3PAT?$__vector@M$02@__clang@@A", i32 16), i32 2), align 8       
  ret void
}
```
### CallInst (DXILOP and other cases)

Finally the `CallInst` cases is really just to cover HLSL intrinsics. However it 
needs to also be able to lower all mathimatical and logical operations like
`add`, `mul`, `and`, etc.

This is another case where useing the scalarizer pass would save us time. However, the scalarizer pass will only work on llvm intrinsics and not `@dx.op`.
This means this part of scalarization would have to happen before `DXILOpLowering`.

#### DXIL OP CallInst example
```cpp
export float4 fn(float4 a) {
  return cos(sin(a));
}
```
```llvm
define noundef <4 x float> @cos_sin_float_test(<4 x float> noundef %0) {
  %2 = tail call <4 x float> @llvm.sin.v4f32(<4 x float> %0)
  %3 = tail call <4 x float> @llvm.cos.v4f32(<4 x float> %2)
  ret <4 x float> %3
}
```
```powershell
<build_path>\bin\opt.exe -S -passes=scalarizer -scalarize-variable-insert-extract .\llvm\test\CodeGen\DirectX\scalarize2.ll
```
This pass handles both the extract\insert interleaving if it was just one intrinsics as preventing the inclusion of unecessary extract\inserts.
```llvm
define noundef <4 x float> @cos_sin_float_test(<4 x float> noundef %0) {
  %.i0 = extractelement <4 x float> %0, i64 0
  %.i01 = call float @llvm.sin.f32(float %.i0)
  %.i1 = extractelement <4 x float> %0, i64 1
  %.i12 = call float @llvm.sin.f32(float %.i1)
  %.i2 = extractelement <4 x float> %0, i64 2
  %.i23 = call float @llvm.sin.f32(float %.i2)
  %.i3 = extractelement <4 x float> %0, i64 3
  %.i34 = call float @llvm.sin.f32(float %.i3)
  %.i05 = call float @llvm.cos.f32(float %.i01)
  %.i16 = call float @llvm.cos.f32(float %.i12)
  %.i27 = call float @llvm.cos.f32(float %.i23)
  %.i38 = call float @llvm.cos.f32(float %.i34)
  %.upto09 = insertelement <4 x float> poison, float %.i05, i64 0
  %.upto110 = insertelement <4 x float> %.upto09, float %.i16, i64 1
  %.upto211 = insertelement <4 x float> %.upto110, float %.i27, i64 2
  %2 = insertelement <4 x float> %.upto211, float %.i38, i64 3
  ret <4 x float> %2
}
```

#### Example 2 Cleanup
The scalarizer pass also can do cleanup for us if say our DXIL expansion pass adds to many insert\extracts

```llvm
define noundef <4 x float> @cos_sin_float_test2(<4 x float> noundef %a) {
  %1 = extractelement <4 x float> %a, i64 0
  %Sin = call float  @llvm.sin.f32(float %1)
  %2 = insertelement <4 x float> undef, float %Sin, i64 0
  %3 = extractelement <4 x float> %a, i64 1
  %Sin1 = call float  @llvm.sin.f32(float %3)
  %4 = insertelement <4 x float> %2, float %Sin1, i64 1
  %5 = extractelement <4 x float> %a, i64 2
  %Sin2 = call float  @llvm.sin.f32(float %5)
  %6 = insertelement <4 x float> %4, float %Sin2, i64 2
  %7 = extractelement <4 x float> %a, i64 3
  %Sin3 = call float  @llvm.sin.f32(float %7)
  %8 = insertelement <4 x float> %6, float %Sin3, i64 3
   %9 = extractelement <4 x float> %a, i64 0
  %Cos = call float  @llvm.cos.f32(float %9)
  %10 = insertelement <4 x float> undef, float %Cos, i64 0
  %11 = extractelement <4 x float> %a, i64 1
  %Cos1 = call float  @llvm.cos.f32(float %11)
  %12 = insertelement <4 x float> %10, float %Cos1, i64 1
  %13 = extractelement <4 x float> %a, i64 2
  %Cos2 = call float  @llvm.cos.f32(float %13)
  %14 = insertelement <4 x float> %12, float %Cos2, i64 2
  %15 = extractelement <4 x float> %a, i64 3
  %Cos3 = call float  @llvm.cos.f32(float %15)
  %16 = insertelement <4 x float> %14, float %Cos3, i64 3
  ret <4 x float> %16
}
```
Will become
```llvm
define noundef <4 x float> @cos_sin_float_test2(<4 x float> noundef %a) {
  %a.i3 = extractelement <4 x float> %a, i64 3
  %a.i2 = extractelement <4 x float> %a, i64 2
  %a.i1 = extractelement <4 x float> %a, i64 1
  %a.i0 = extractelement <4 x float> %a, i64 0
  %Cos = call float @llvm.cos.f32(float %a.i0)
  %Cos1 = call float @llvm.cos.f32(float %a.i1)
  %Cos2 = call float @llvm.cos.f32(float %a.i2)
  %Cos3 = call float @llvm.cos.f32(float %a.i3)
  %.upto016 = insertelement <4 x float> poison, float %Cos, i64 0
  %.upto117 = insertelement <4 x float> %.upto016, float %Cos1, i64 1
  %.upto218 = insertelement <4 x float> %.upto117, float %Cos2, i64 2
  %1 = insertelement <4 x float> %.upto218, float %Cos3, i64 3
  ret <4 x float> %1
}
```
#### Example 3 add and mul
```llvm
define <4 x float> @add_float_int(<4 x float> %0, <4 x float> %1)  {
  %4 = fadd <4 x float> %0, %1
  ret <4 x float> %4
}

define <4 x float> @mul_float_int(<4 x float> %0, <4 x float> %1)  {
  %4 = fmul <4 x float> %0, %1
  ret <4 x float> %4
}
```

with scalarize pass Becomes
```llvm
define <4 x float> @add_float_int(<4 x float> %0, <4 x float> %1) {
  %.i0 = extractelement <4 x float> %0, i64 0
  %.i01 = extractelement <4 x float> %1, i64 0
  %.i02 = fadd float %.i0, %.i01
  %.i1 = extractelement <4 x float> %0, i64 1
  %.i13 = extractelement <4 x float> %1, i64 1
  %.i14 = fadd float %.i1, %.i13
  %.i2 = extractelement <4 x float> %0, i64 2
  %.i25 = extractelement <4 x float> %1, i64 2
  %.i26 = fadd float %.i2, %.i25
  %.i3 = extractelement <4 x float> %0, i64 3
  %.i37 = extractelement <4 x float> %1, i64 3
  %.i38 = fadd float %.i3, %.i37
  %.upto0 = insertelement <4 x float> poison, float %.i02, i64 0
  %.upto1 = insertelement <4 x float> %.upto0, float %.i14, i64 1
  %.upto2 = insertelement <4 x float> %.upto1, float %.i26, i64 2
  %3 = insertelement <4 x float> %.upto2, float %.i38, i64 3
  ret <4 x float> %3
}

define <4 x float> @mul_float_int(<4 x float> %0, <4 x float> %1) {
  %.i0 = extractelement <4 x float> %0, i64 0
  %.i01 = extractelement <4 x float> %1, i64 0
  %.i02 = fmul float %.i0, %.i01
  %.i1 = extractelement <4 x float> %0, i64 1
  %.i13 = extractelement <4 x float> %1, i64 1
  %.i14 = fmul float %.i1, %.i13
  %.i2 = extractelement <4 x float> %0, i64 2
  %.i25 = extractelement <4 x float> %1, i64 2
  %.i26 = fmul float %.i2, %.i25
  %.i3 = extractelement <4 x float> %0, i64 3
  %.i37 = extractelement <4 x float> %1, i64 3
  %.i38 = fmul float %.i3, %.i37
  %.upto0 = insertelement <4 x float> poison, float %.i02, i64 0
  %.upto1 = insertelement <4 x float> %.upto0, float %.i14, i64 1
  %.upto2 = insertelement <4 x float> %.upto1, float %.i26, i64 2
  %3 = insertelement <4 x float> %.upto2, float %.i38, i64 3
  ret <4 x float> %3
}
```

### BitCast
Bitcast gets scalarized on a per element basis if we use the `scalarize-variable-insert-extract` pass\flag. It however does modify
the bitcasts to the ones used in DXC\llvm3.7. Namely DXC would emit
`sitofp`, `uitofp`, `fptosi`, & `fptoui`. We might need a clean up pass here to
swap out `bitcast` for the mentioned cases.

#### Example
```llvm
define <4 x float> @add_float_int(<4 x float> %0, <4 x i32> %1)  {
  %3 = bitcast <4 x i32> %1 to <4 x float>
  %4 = fadd <4 x float> %0, %3
  ret <4 x float> %4
}

define <4 x float> @mul_float_int(<4 x float> %0, <4 x i32> %1)  {
  %3 = bitcast <4 x i32> %1 to <4 x float>
  %4 = fmul <4 x float> %0, %3
  ret <4 x float> %4
}
```
Becomes
```llvm

define <4 x float> @add_float_int(<4 x float> %0, <4 x i32> %1) {
  %.i05 = extractelement <4 x float> %0, i64 0
  %.i17 = extractelement <4 x float> %0, i64 1
  %.i29 = extractelement <4 x float> %0, i64 2
  %.i311 = extractelement <4 x float> %0, i64 3
  %.i0 = extractelement <4 x i32> %1, i64 0
  %.i01 = bitcast i32 %.i0 to float
  %.i1 = extractelement <4 x i32> %1, i64 1
  %.i12 = bitcast i32 %.i1 to float
  %.i2 = extractelement <4 x i32> %1, i64 2
  %.i23 = bitcast i32 %.i2 to float
  %.i3 = extractelement <4 x i32> %1, i64 3
  %.i34 = bitcast i32 %.i3 to float
  %.i06 = fadd float %.i05, %.i01
  %.i18 = fadd float %.i17, %.i12
  %.i210 = fadd float %.i29, %.i23
  %.i312 = fadd float %.i311, %.i34
  %.upto013 = insertelement <4 x float> poison, float %.i06, i64 0
  %.upto114 = insertelement <4 x float> %.upto013, float %.i18, i64 1
  %.upto215 = insertelement <4 x float> %.upto114, float %.i210, i64 2
  %3 = insertelement <4 x float> %.upto215, float %.i312, i64 3
  ret <4 x float> %3
}

define <4 x float> @mul_float_int(<4 x float> %0, <4 x i32> %1) {
  %.i05 = extractelement <4 x float> %0, i64 0
  %.i17 = extractelement <4 x float> %0, i64 1
  %.i29 = extractelement <4 x float> %0, i64 2
  %.i311 = extractelement <4 x float> %0, i64 3
  %.i0 = extractelement <4 x i32> %1, i64 0
  %.i01 = bitcast i32 %.i0 to float
  %.i1 = extractelement <4 x i32> %1, i64 1
  %.i12 = bitcast i32 %.i1 to float
  %.i2 = extractelement <4 x i32> %1, i64 2
  %.i23 = bitcast i32 %.i2 to float
  %.i3 = extractelement <4 x i32> %1, i64 3
  %.i34 = bitcast i32 %.i3 to float
  %.i06 = fmul float %.i05, %.i01
  %.i18 = fmul float %.i17, %.i12
  %.i210 = fmul float %.i29, %.i23
  %.i312 = fmul float %.i311, %.i34
  %.upto013 = insertelement <4 x float> poison, float %.i06, i64 0
  %.upto114 = insertelement <4 x float> %.upto013, float %.i18, i64 1
  %.upto215 = insertelement <4 x float> %.upto114, float %.i210, i64 2
  %3 = insertelement <4 x float> %.upto215, float %.i312, i64 3
  ret <4 x float> %3
}
```

## Priority of work
As mentioned in the background section. DXC handles 8 instructions for scalarization. We know that `BitCastInst`, `CallInst`, `LoadInst` and `StoreInst`
Are largely handled for us if we use the `scalarizer` pass with the `-scalarize-load-store` and `-scalarize-variable-insert-extract` flags. And we probably don't need to handle the `AddrSpaceCastInst` case. Allocas could be handled by running SROA. So thats 6/8 cases
just by using an existing pass. 

There are a few ways we could go about this:
1. support `PassInfoMixin` in the DirectX backend. 
   - Need to override "buildCodeGenPipeline" for the DirectX backend.
2. Add a Legacy Pass manager abstraction to `scalarizer`
   - Do we need permission to do this? Do we need an RFC?
3. Fork the `scalarizer` so we can have a legacy and `PassInfoMixin` in the DirectX Backend?
   - We could make this work for dxil ops and not just intrinsics.

The next work wold be cleanup for Bitcast.

The next would be to add SROA. This is a one line change. However we need
some good test cases and thats where I imagine a few days of work will be.

## Areas explicitly ignored
SROA_Parameter pass has some  matrix loads and stores that this proposal won't go into.
It also looks to do some legalization via `LegalizeDxilInputOutputs` that won't be covered.

## Tickets
Tickets 1-3 and 5 can be handled via the Scalarization pass. If we are in agrement
then these are just one ticket.
1. ~~Create a scalarization pass that just handles the flattenArgument case to start.~~      
    - ~~To simplify things "workists" will just be HLSL intrinsics.~~
    - ~~We iterate over all intrinsics and iterate over all value uses~~
    - ~~For now the only value we will check for are `CallInst`~~
    - ~~The pass will replace intrinsics used by DXIL.td that are a multi-element 
    call with multiple scalarized calls~~
2. ~~Expand the scalar expansion pass to handle `loads` by checking for `LoadInst`~~
   - ~~handle the vector load case~~
   - ~~handle the Agregate Vector\Struct Array load case~~
   - ~~handle the Agregate scalar load case~~
3. ~~Expand the scalar expansion pass to handle `stores` by checking for `StoreInst`~~
   - ~~handle the vector store case~~
   - ~~handle the Agregate Vector\Struct Array store case~~
   - ~~handle the Agregate scalar store case~~
4. Expand the scalar expansion pass to handle Geps by checking for `GetElementPtrInst` likely via the `visitGetElementPtrInst` pattern
5. ~~Expand the scalar expansion pass to handle  bit casts by checking for `BitCastInst` likely via the ``visitBitCastInst` pattern~~
6. Expand the scalar expansio pass to handle scalaiarize mem operations by checking for `MemIntrinsic`
   - Investigate how to handle memcpy, SROA only has visis for memset and mem transfer via `visitMemSetInst`, & `visitMemTransferInst`.
7. Handle the `GlobalAndAllocas` cases

## Appendix

### Background on DXC Behavior
In DXC the scalarization pass looks  something like this:
```
SROA_Parameter_HLSL::runOnModule 
|-> LegalizeDxilInputOutputs
|-> RewriteBitcastWithIdenticalStructs
|-> createFlattenedFunction  
    |-> flattenArgument -> DoScalarReplacement
    |-> special matrix load stores
    |-> LegalizeDxilInputOutputs
|-> SROAGlobalAndAllocas -> DoScalarReplacement -> RewriteForScalarRepl


 _________________________________________RewriteForScalarRepl_________________________________________________              <------------------|
/                    /              /              |               \               \            |              \                                |
RewriteForConstExpr  RewriteForGEP  RewriteForLoad RewriteForStore RewriteMemIntrin RewriteCall RewriteBitCast  RewriteForAddrSpaceCast         |
                                                                                    /          |___                                   |_______  |
                                                                                    RewriteCallArg |-> RewriteWithFlattenedHLIntrinsicCall    |-|
```

#### RewriteForConstExpr
Recursively "flatten" a constant expression (ConstantExpr) in LLVM IR. 
It checks if the expression is either a GEPOperator (GEP instruction) or an AddrSpaceCast
If the expression is used by an instruction, it converts the ConstantExpr 
into an instruction and replaces the use with this new instruction.

#### RewriteForGEP
A function designed to "rewrite" a GetElementPtr (GEP) instruction to make it 
relative to a new element, usually when dealing with structs, vectors, or arrays.
for the struct  case when a matching element is found, it simplifies the GEP 
by updating its base pointer and indices. If no such element exists, new GEPs 
are created for each element in an array or vector and replaces the old GEP 
accordingly. The function ensures that the new GEP has the correct type &
replaces all uses of the original GEP. After rewriting, the old GEP is either
destroyed or marked for deletion. The goal is to to break down and flatten
complex memory access patterns in IR.

 #### RewriteForLoad
Three cases:
 1. // Replace for Vector:
```
    //   %res = load { 2 x i32 }* %alloc
    // with:
    //   %load.0 = load i32* %alloc.0
    //   %insert.0 insertvalue { 2 x i32 } zeroinitializer, i32 %load.0, 0
    //   %load.1 = load i32* %alloc.1
    //   %insert = insertvalue { 2 x i32 } %insert.0, i32 %load.1, 1
```
 2. // Replace for Agregate Vector\Struct Array:
```
      //   %res = load [2 x <2 x float>] * %alloc
      // with:
      //   %load.0 = load [4 x float]* %alloc.0
      //   %insert.0 insertvalue [4 x float] zeroinitializer,i32 %load.0,0
      //   %load.1 = load [4 x float]* %alloc.1
      //   %insert = insertvalue [4 x float] %insert.0, i32 %load.1, 1
      //  ...
```
3. // Replace for Aggregate loads:
```
      //   %res = load { i32, i32 }* %alloc
      // with:
      //   %load.0 = load i32* %alloc.0
      //   %insert.0 insertvalue { i32, i32 } zeroinitializer, i32 %load.0,
      //   0
      //   %load.1 = load i32* %alloc.1
      //   %insert = insertvalue { i32, i32 } %insert.0, i32 %load.1, 1
      // (Also works for arrays instead of structs)
```
#### RewriteForStore
1. // Replace for Vector:
```
    //   store <2 x float> %val, <2 x float>* %alloc
    // with:
    //   %val.0 = extractelement { 2 x float } %val, 0
    //   store i32 %val.0, i32* %alloc.0
    //   %val.1 = extractelement { 2 x float } %val, 1
    //   store i32 %val.1, i32* %alloc.1
```
2. // Replace for Agregate Vector\Struct Array:
```
      //   store [2 x <2 x i32>] %val, [2 x <2 x i32>]* %alloc, align 16
      // with:
      //   %val.0 = extractvalue [2 x <2 x i32>] %val, 0
      //   %all0c.0.0 = getelementptr inbounds [2 x i32], [2 x i32]* %alloc.0,
      //   i32 0, i32 0
      //   %val.0.0 = extractelement <2 x i32> %243, i64 0
      //   store i32 %val.0.0, i32* %all0c.0.0
      //   %alloc.1.0 = getelementptr inbounds [2 x i32], [2 x i32]* %alloc.1,
      //   i32 0, i32 0
      //   %val.0.1 = extractelement <2 x i32> %243, i64 1
      //   store i32 %val.0.1, i32* %alloc.1.0
      //   %val.1 = extractvalue [2 x <2 x i32>] %val, 1
      //   %alloc.0.0 = getelementptr inbounds [2 x i32], [2 x i32]* %alloc.0,
      //   i32 0, i32 1
      //   %val.1.0 = extractelement <2 x i32> %248, i64 0
      //   store i32 %val.1.0, i32* %alloc.0.0
      //   %all0c.1.1 = getelementptr inbounds [2 x i32], [2 x i32]* %alloc.1,
      //   i32 0, i32 1
      //   %val.1.1 = extractelement <2 x i32> %248, i64 1
      //   store i32 %val.1.1, i32* %all0c.1.1
```
3. // Replace for Aggregate stores:
```
      //   store { i32, i32 } %val, { i32, i32 }* %alloc
      // with:
      //   %val.0 = extractvalue { i32, i32 } %val, 0
      //   store i32 %val.0, i32* %alloc.0
      //   %val.1 = extractvalue { i32, i32 } %val, 1
      //   store i32 %val.1, i32* %alloc.1
      // (Also works for arrays instead of structs)
```

#### RewriteMemIntrin
rewriting memory intrinsics (memcpy, memset, memmove) when dealing with scalarized memory. 
The goal is to decompose the memory intrinsic operation into element-wise operations that 
apply to each scalar element of the memory being accessed.

#### RewriteCall
This pass rewrites function calls into either `RewriteCallArg`or `RewriteWithFlattenedHLIntrinsicCall`
The default case is `RewriteWithFlattenedHLIntrinsicCall`. `RewriteCallArg` 
is primarily used in ray tracing intrinsics like `TraceRay` `ReportHit`, and `CallShader`.

##### RewriteCallArg
This function does not operate on flattened (scalarized) data structures,
this function replaces the original pointer argument (OldVal) with a stack-allocated 
(alloca) pointer and manages the transfer of data between the original pointer and the alloca.
- bIn (Copy-In): If bIn then copy the data from the original pointer to the alloca before the function call.
- bOut (Copy-Out): If bOut then copy data back from the alloca to the original pointer after the function call.

##### RewriteWithFlattenedHLIntrinsicCall
This function is used to replace a multi-element call with multiple scalarized calls

#### RewriteBitCast
The RewriteBitCast function processes BitCastInst instructions in LLVM IR:
1. Remove Unused Bitcasts: If the bitcast is not used, it is removed.
2. Check and Process Pointer Types: Ensures both source and destination types 
are pointers.
3. Handle Non-Struct Types: If the destination type is not a struct, replace 
the bitcast with intrinsics for each element if it’s used by lifetime markers.
4 Handle Struct Types: If both types are structs, verify type compatibility. 
If compatible, replace the bitcast with a GEP instruction for efficient access; 
otherwise, handle errors.
5. Finalize: Ensure the bitcast is replaced or removed, and if needed, process 
the resulting GEP instruction further.
Note: its heavily used to remove lifetime intrinsics.

#### RewriteForAddrSpaceCast
processes AddrSpaceCast instructions in LLVM IR:
1. Initialize: Sets up a vector to store new AddrSpaceCast values.
2. Create New Casts: For each element in NewElts, a new AddrSpaceCast is created
 with the appropriate address space and added to the vector.
3. Scalar Replacement: Uses an SROA_Helper object to perform scalar replacement
 for the original cast.
4. Cleanup: Ensures that the original AddrSpaceCast is no longer used and 
removes or destroys it accordingly.
The goal of this helper is to handle the transformation and cleanup of 
AddrSpaceCast operations,replacing old casts with new ones.

## HLSL specific SROA Behavior Differences
- [Disable **ForceSSAUpdater** and **SROAStrictInbounds**](https://github.com/microsoft/DirectXShaderCompiler/blob/e0fbce714da4746477639d82185ae76f6df4f472/lib/Transforms/Scalar/SROA.cpp#L83C1-L102C1)
- [`visitBitCastInst` HLSL type handling](https://github.com/microsoft/DirectXShaderCompiler/blob/e0fbce714da4746477639d82185ae76f6df4f472/lib/Transforms/Scalar/SROA.cpp#L710C5-L716C24)
- [`visitLoadInst` HLSL type handling](https://github.com/microsoft/DirectXShaderCompiler/blob/e0fbce714da4746477639d82185ae76f6df4f472/lib/Transforms/Scalar/SROA.cpp#L777C5-L780C24)
- [`visitStoreInst` HLSL type handling](https://github.com/microsoft/DirectXShaderCompiler/blob/e0fbce714da4746477639d82185ae76f6df4f472/lib/Transforms/Scalar/SROA.cpp#L797C5-L800C24)
- [Disable **SROARandomShuffleSlices**](https://github.com/microsoft/DirectXShaderCompiler/blob/e0fbce714da4746477639d82185ae76f6df4f472/lib/Transforms/Scalar/SROA.cpp#L1063C1-L1070C44)
- [Another `visitLoadInst` HLSL type handling](https://github.com/microsoft/DirectXShaderCompiler/blob/e0fbce714da4746477639d82185ae76f6df4f472/lib/Transforms/Scalar/SROA.cpp#L3366C5-L3369C24)
- [Another `visitStoreInst` HLSL type handling](https://github.com/microsoft/DirectXShaderCompiler/blob/e0fbce714da4746477639d82185ae76f6df4f472/lib/Transforms/Scalar/SROA.cpp#L3404C5-L3407C24)
- [Another `visitBitCastInst` HLSL type handling](https://github.com/microsoft/DirectXShaderCompiler/blob/e0fbce714da4746477639d82185ae76f6df4f472/lib/Transforms/Scalar/SROA.cpp#L3417C5-L3422C24)
- [Debug layout for stride](https://github.com/microsoft/DirectXShaderCompiler/blob/e0fbce714da4746477639d82185ae76f6df4f472/lib/Transforms/Scalar/SROA.cpp#L4303C5-L4317C24)
- Major change to handle strides [DXC:SROA4324-4352](https://github.com/microsoft/DirectXShaderCompiler/blob/e0fbce714da4746477639d82185ae76f6df4f472/lib/Transforms/Scalar/SROA.cpp#L4324C1-L4352C20)
- [ignore bool `alloca(s)`](https://github.com/microsoft/DirectXShaderCompiler/blob/e0fbce714da4746477639d82185ae76f6df4f472/lib/Transforms/Scalar/SROA.cpp#L4398C3-L4404C21)
- [skip alloca for HLSL types](https://github.com/microsoft/DirectXShaderCompiler/blob/e0fbce714da4746477639d82185ae76f6df4f472/lib/Transforms/Scalar/SROA.cpp#L4410C7-L4412C26)
- [move `dbg.declare(s)` removal to before `replaceAllUsesWith`](https://github.com/microsoft/DirectXShaderCompiler/blob/e0fbce714da4746477639d82185ae76f6df4f472/lib/Transforms/Scalar/SROA.cpp#L4479C5-L4488C24)
- [Disables original removal of `dbg.declare(s)`](https://github.com/microsoft/DirectXShaderCompiler/blob/e0fbce714da4746477639d82185ae76f6df4f472/lib/Transforms/Scalar/SROA.cpp#L4500C1-L4506C22)

## SROA Behavior as exists in DXC
The Call graph below performs 3 main functions
![](dxil-scalarization-assets/SROA_call_graph.png)
1. **Populate a list of Allocas**: It populates a worklist with alloca instructions (memory allocations) from the function's entry block.
2. **Processing Allocas**: For each alloca in the worklist, `runOnAlloca` performs 
various transformations:
- - Handles dead allocas and special cases.
  - Rewrites aggregate loads and stores.
  - Splits allocas into smaller pieces (slices) and handles dead users and 
  operands.
  - Speculates on PHI and select instructions for further optimization 
  opportunities.
3. Promotion and Cleanup: After processing allocas, it promotes them to registers if possible (`promoteAllocas`), then deletes any instructions marked as dead (`deleteDeadInstructions`).


### SROA::runOnFunction(Function &F)

- This function attempts to run the SROA optimization on the given function F.
It has a loop that runs up to three times (kMaxCount), calling `runOnFunctionImp(F)` each time.
- If `runOnFunctionImp(F)` returns false, the loop breaks early. It returns 
true if the function was modified in at least one of the iterations, otherwise 
it returns false.

### SROA::runOnFunctionImp(Function &F)

- This function performs the actual SROA optimization.
It first checks if the function should be skipped by calling skipOptnoneFunction(F).
- It sets up some analysis passes like Dominator Tree and Assumption Cache.
- It initializes the Worklist with alloca instructions from the entry block of 
the function.
- It then iterates over the worklist, calling `runOnAlloca` for each alloca and
 managing a set of deleted allocas to avoid reprocessing them.
- It promotes allocas using `promoteAllocas(F)`.
- It loops until the worklist is empty and returns true if any changes were 
made.

### SROA::runOnAlloca(AllocaInst &AI)

This function performs SROA on a single alloca instruction.
- It first handles dead allocas and special cases, such as those with types it cannot process.
- It rewrites aggregate loads and stores via AggLoadStoreRewriter.
- It builds slices of the alloca using AllocaSlices.
- It deletes dead users and operands of the alloca.
- It splits the alloca if possible, and speculates on PHIs and select instructions.
- Returns true if any changes were made.

### SROA::deleteDeadInstructions(SmallPtrSetImpl<AllocaInst > &DeletedAllocas)

- This function deletes instructions that have been marked as dead.
- It handles special cases for alloca instructions by removing related 
`dbg.declare` instructions.
- It replaces all uses of the dead instruction with undef.
- It recursively checks the operands of the dead instruction to see if they 
also become dead.
- It increments a counter for the number of deleted instructions and removes 
the instruction from the parent.
