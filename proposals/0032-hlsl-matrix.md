---
title: 0032 - HLSL Matrices
params:
  authors:
  + farzonl: Farzon Lotfi
  + pow2clk: Greg Roth
  status: Design In Progress
---

# HLSL Matrices
* Issues:
  [#88060](https://github.com/llvm/llvm-project/issues/88060)

## Introduction

Adding native matrix types is critical for modernizing HLSL. Matrices are core
to graphics workloads, powering transformations, lighting, and animation. For
the frontend mapping HLSL matrices to Clang's Matrix Type Extension allows us
to build on an existing type with clean IR that maps to vectors and will
unlock effective optimizations, while simplifying backend lowering. This change
makes HLSL matrices a first-class citizen in LLVM, improving portability and
long-term maintainability.

## Requirements

HLSL matrices must:
* Be limited to dimensions of 1-4 inclusive.
* Have initialization using vectors, scalars or a single splatted scalar.
* Determine orientation via (row|column)_major qualifiers.
* Have orientation-appropriate column or row access using a single subscript operator
* Zero-based ( `._m<row><col>`) and one-based (`._<row><col>`) point accessors
* Support for all piecewise comparison operators
* Piecewise division by a scalar.
* Boolean matrices with full operator support
* Implicit element type conversions allowing operations on matrices of different
  element types.
* When both destination dimensions are less than or equal to the source, 
  matrices can be implicitly truncated to smaller sizes with a warning.
* Usable as resource element types
* Usable as entry point semantics
* Matrix multiplication with compatible vectors
* Resolve overloaded functions taking matrix parameters.

## Solution

The Clang matrix extension gives us the frontend support we need to build HLSL
matrices. We will essentially map the matrix keyword to the `matrix_type`

attribute using semantics.

```hlsl
template<typename Ty, int R, int C> using matrix = Ty
  __attribute__((matrix_type(R,C)));
```

Then typedef the specific types we need to account for the 1 through 4 
inclusive matrix types we need

```hlsl
typedef matrix<float, 4, 4> float4x4;
```

We will need to do this in sema source to make this type available before we
start parsing headers. This will be done similar to `defineHLSLVectorAlias()` in 
`HLSLExternalSemaSource.cpp` .

Advantages to using Clang matrix extension is that it lowers to Clang Vector
types meaning we won't have to change much of our backend like the intrinsic
expansions and the scalarizer to account for a new type.
Other advantages include:
* Declare matrices in different scopes (local, global, param, templates, etc)
* Pass matrices as parameters
* Return from functions
* Lower to vector representations
* Load as column/row major
* Perform most piecewise operations with splatted scalars (missing divide)
* Explicit casts between matrices with all compatible element types

Another advantage is the elements of a value of a `matrix_type` are laid out in
[column-major order](https://clang.llvm.org/docs/MatrixTypes.html#decisions-for-the-implementation-in-clang) without padding. 
That exactly matches the memory layout we need for the DirectX backend without
 having to add any special passes to manipulate data layout.

That said the current `matrix_type` has a complication. The current design is 
incomplete with an intent to be row\col major agnostic. The plan is to support
both data layouts in a way where accessing columns or rows can be done 
efficiently, but not both. That could present problems with supporting
(row|column)_major qualifiers in the same shader.

Other complications we will need to account for are the legalization of matrix
intrinsics types like:
* int_matrix_transpose
* int_matrix_multiply
* int_matrix_column_major_load
* int_matrix_column_major_store

For matrix multiply we will need to do a replacement in intrinsic
expansion to a vector fmuls and FMads.
https://godbolt.org/z/PqzWr1r53

Also `*` and the hlsl intrinsic `mul` are different.
`*` is an elementwise multiplication and so
`float4x2` will only multiply with another `float4x2` .
Mul will do multiplications so a `float4x2` will multiply with a `float2x4` .

For transpose we will need a legalization for the intrinsic.
https://godbolt.org/z/6xGY3hn8Y

For column_major_{load|store} intrinsics this will need to be associated with 
HLSL's `column_major` attribute on the type in the resource. We will likely
need to make sure clang doesn't drop the annotation until we emit this
intrinsic. Then in the DirectX backend legalize this intrinsic to impact 
orientation-aware load and store operations.

A remaining complication is what to do with the Type Printer. Instead of overriding
clang/lib/AST/TypePrinter.cpp for matrix extension types it might make sense for
HLSL matrices to print completely separately.

This is a rough sketch of how I was thinking to address the issues raised
in https://github.com/llvm/llvm-project/pull/111415

```cpp
// In TypePrinter.cpp
static void printDims(const ConstantMatrixType *T, raw_ostream &OS) {
  OS << T->getNumRows() << ", " << T->getNumColumns();
}

void TypePrinter::printHLSLMatrixBefore(const ConstantMatrixType *T, raw_ostream &OS) {
  OS << "matrix<";
  printBefore(T->getElementType(), OS);
}

void TypePrinter::printHLSLMatrixAfter(const ConstantMatrixType *T, raw_ostream &OS) {
  OS << ", ";
  printDims(T, OS);
  OS << ">";
}

void TypePrinter::printClangMatrixBefore(const ConstantMatrixType *T, raw_ostream &OS) {
  printBefore(T->getElementType(), OS);
  OS << " __attribute__((matrix_type(";
  printDims(T, OS);
  OS << ")))";
}

void TypePrinter::printConstantMatrixBefore(const ConstantMatrixType *T, raw_ostream &OS) {
  if (Policy.UseHLSLTypes) {
    printHLSLMatrixBefore(T, OS);
    return;
  }
  printClangMatrixBefore(T, OS);
}

void TypePrinter::printConstantMatrixAfter(const ConstantMatrixType *T, raw_ostream &OS) {
  if (Policy.UseHLSLTypes) {
    printHLSLMatrixAfter(T, OS);
    return;
  }
  printAfter(T->getElementType(), OS);
}
```

## Testing

To land just the clang extention the testing will be simplified to what was 
done for [vectors](https://github.com/llvm/llvm-project/commit/b8dbc6ffea93976dc0d8569c9d23e9c21e33e317).

Testing for operators should not be necessary those tests already exist for 
clang matrix extentions. All the HLSL matrix must cases should be captured in
the offload test suite.
