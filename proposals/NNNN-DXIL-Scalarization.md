# DXIL Scalarization

* Proposal: [NNNN](NNNN-DXIL-Scalarization.md)
* Author(s): [Farzon Lotfi](https://github.com/farzonl)
* Sponsor: [Farzon Lotfi](https://github.com/farzonl)
* Status: **Under Consideration**
* Impacted Projects: Clang

## Introduction
As mentioned in [DXIL.rst](https://github.com/microsoft/DirectXShaderCompiler/blob/main/docs/DXIL.rst#vectors) 
"HLSL vectors are scalarized" and "Matrices are lowered to vectors". Therefore,
 we need to be able to scalarize these types in clang DirectX backend. Today 
this is done via [`SROA_Parameter_HLSL` Module pass in `ScalarReplAggregatesHLSL.cpp`](https://github.com/microsoft/DirectXShaderCompiler/blob/main/lib/Transforms/Scalar/ScalarReplAggregatesHLSL.cpp#L4263).


## Motivation
Without Scalarizing the data structures and call instructions we can't generate valid DXIL.

## Background
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

### RewriteForConstExpr
Recursively "flatten" a constant expression (ConstantExpr) in LLVM IR. 
It checks if the expression is either a GEPOperator (GEP instruction) or an AddrSpaceCast
If the expression is used by an instruction, it converts the ConstantExpr 
into an instruction and replaces the use with this new instruction.

### RewriteForGEP
 A function designed to "rewrite" a GetElementPtr (GEP) instruction to make it 
 relative to a new element, usually when dealing with structs, vectors, or arrays.
 for the struct  case when a matching element is found, it simplifies the GEP 
 by updating its base pointer and indices. If no such element exists, new GEPs 
 are created for each element in an array or vector and replaces the old GEP 
 accordingly. The function ensures that the new GEP has the correct type &
 replaces all uses of the original GEP. After rewriting, the old GEP is either
 destroyed or marked for deletion. The goal is to to break down and flatten
 complex memory access patterns in IR.

 ### RewriteForLoad
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
### RewriteForStore
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

### RewriteMemIntrin
rewriting memory intrinsics (memcpy, memset, memmove) when dealing with scalarized memory. 
The goal is to decompose the memory intrinsic operation into element-wise operations that 
apply to each scalar element of the memory being accessed.

### RewriteCall
This pass rewrites function calls into either `RewriteCallArg`or `RewriteWithFlattenedHLIntrinsicCall`
The default case is `RewriteWithFlattenedHLIntrinsicCall`. `RewriteCallArg` 
is primarily used in ray tracing intrinsics like `TraceRay` `ReportHit`, and `CallShader`.

#### RewriteCallArg
This function does not operate on flattened (scalarized) data structures,
 this function replaces the original pointer argument (OldVal) with a stack-allocated 
 (alloca) pointer and manages the transfer of data between the original pointer and the alloca.
- bIn (Copy-In): If bIn then copy the data from the original pointer to the alloca before the function call.
- bOut (Copy-Out): If bOut then copy data back from the alloca to the original pointer after the function call.

#### RewriteWithFlattenedHLIntrinsicCall
This function is used to replace a multi-element call with multiple scalarized calls

### RewriteBitCast
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

### RewriteForAddrSpaceCast
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


## Priority of work
The rewrite functions specified above are the piece of DXC we need to bring over
for scalarization. `RewriteForScalarRepl` works on two sets of data globals\allocas 
and function arguments.

The port should start with a compatible alternative to `RewriteCall` 
specifically `RewriteWithFlattenedHLIntrinsicCall`As the other pieces are not needed 
for compute shaders.Next would be `RewriteForLoad` and `RewriteForStore` as those 
transformations are need to properlyhandle resources and are very well defined in 
their outcomes. Then  `RewriteForGEP` and `RewriteForAddrSpaceCast`. Once those 
are defined we can tackle `RewriteForConstExpr`  which utilizes both `RewriteForGEP`
 and `RewriteForAddrSpaceCast`. Next to elminiate things like life time markers
`RewriteBitCast`. And finally to remove memcpys that could have been added
 we should implement `RewriteMemIntrin`.

## Areas explicitly ignored
SROA_Parameter pass has some  matrix loads and stores that this proposal won't go into.
It also looks to do some legalization via `LegalizeDxilInputOutputs` that won't be covered.


## Tickets
1. Create a scalarization pass that just handles the flattenArgument case to start.      
    - To simplify things "workists" will just be HLSL intrinsics.
    - We iterate over all intrinsics and iterate over all value uses
    - For now the only value we will check for are `CallInst`
    - The pass will replace intrinsics used by DXIL.td that are a multi-element 
    call with multiple scalarized calls
2. Expand the scalar expansion pass to handle `loads` by checking for `LoadInst`
   - handle the vector load case
   - handle the Agregate Vector\Struct Array load case
   - handle the Agregate scalar load case
3. Expand the scalar expansion pass to handle `stores` by checking for `StoreInst`
   - handle the vector store case
   - handle the Agregate Vector\Struct Array store case
   - handle the Agregate scalar store case
4. Expand the scalar expansion pass to handle Geps by checking for `GetElementPtrInst`
5. Expand the scalar expansion pass to handle Address cases by checking for `AddrSpaceCastInst`
6. Expand the scalar expansion pass to handle  bit casts by checking for `BitCastInst`
7. Expand the scalar expansio pass to handle scalaiarize mem operations by checking for `MemIntrinsic`
8. Handle the `GlobalAndAllocas` cases
