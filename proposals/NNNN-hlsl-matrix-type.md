<!-- {% raw %} -->

# HLSL Constant Matrices

* Proposal: [NNNN](NNNN-hlsl-matrix-type.md)
* Author(s): [Greg Roth](https://github.com/pow2clk)
* Status: **Design In Progress**

* Issues:
  [#88060](https://github.com/llvm/llvm-project/issues/88060)

## Introduction

LLVM matrix support differs in some key ways from the features and limiations
of HLSL matrices. This proposes inheriting from the existing matrix type that
will be enabled in HLSL by default and will impose these limits and allow the
additional capabilities.

## Motivation

Whether transforming geometric coordinates or adapting weights for machine
learning, matrix support is crucial to the existing and future utility of HLSL.
Fortunately, Clang and LLVM support an extension that provides
the fundamentals needed for HLSL matrix support.
However, it is too permissive in the allowable dimensions
and lacking in various other ways that the matrices can be used.

HLSL matrices in DXC have the following features that Clang matrices lack:

* Matrix sizes are limited to dimensions of 1-4 inclusive
* Initialization using vectors, scalars or a single splatted scalar.
* (row|column)_major qualifiers determine orientation
* `#pragma pack_matrix([row|col}_major)` changes the default orientation for
   matrices declared below that line.
* Orientation-appropriate column or row access using a single subscript operator
* Zero-based ( `._m<row><col>`) and one-based (`._<row><col>`.) point accessors
* Support for all piecewise comparison operators
* Support for all piecewise bitwise operators for relevant types
* Piecewise division by a scalar.
* Boolean matrices with full operator support
* Implicit element type conversions allowing operations on matrices of different
  element types.
* When both destination dimensions are less than or equal to the source, 
  matrices can be implicitly truncated to smaller sizes with a warning.
* Usable as resource types
* Usable as entry point semantics
* Matrix multiplication with compatible vectors
* Resolve overloaded functions taking matrix parameters.

Since matrices are represented as vectors,
the following limitations of Clang vectors may also be relevant

* Operators don't accept vectors with different element types
* Boolean vectors are a different type incompatible with other vector types
* Boolean vectors can only be used as operands to logical operators
* Matrices and vectors have evaluation kind TEK_Scalar

## Proposed solution

Leverage Clang matrix support by creating HLSL-specific
matrix types that inherit from the existing matrix extension types.
These types will have methods enabling the additional features and
supporting code will get variants to support the additional capability.

### Leveraging Existing Support

The Clang matrix extension provides us with a strong foundation on which to
build HLSL matrices.
Existing support gives us the ability to:

* Declare matrices in different scopes (local, global, param, templates, etc)
* Pass matrices as parameters
* Return from functions
* Lower to vector representations
* Load as column/row major
* Perform most piecewise operations with splatted scalars (missing divide)
* Explicit casts between matrices with all compatible element types

Though we want to use the existing support, we don't want to mix the matrix types.
HLSL should not allow declarations using the Clang `matrix_type` attribute
and emit an error on the `-fenable-matrix flag`.
HLSL matrices should be available by default when compiling HLSL without
any additional parameters.

### HLSL Matrix Type

The Clang HLSL Matrix Type inherits from the Clang matrix extension
`ConstantMatrixType`.
For many purposes, it can use the same functionality:

* Reading and writing the type out as element type and dimensions
* Determining the size of a matrix variable
* AST traversal and other processing of matrix types
* Lowering to LLVM vectors

It extends that functionality in the following ways to support HLSL features:

* When HLSL is used, dependent sized matrices will be converted to an HLSL
  matrix instead of `ConstantMatrixType`.
* Override dimension checks to limit the sizes to values 1-4.
* Override the element type check to allow for booleans.
* Adds point accessors for 
* Alterations to compatibility checks to allow implicit conversion between
  matrices of different element types including booleans.
* Alterations to compatibility checks to allow truncation of larger to smaller
  dimension matrices.

The HLSL Matrix templated alias is registered as an external source alias.
This allows the full list of accepted matrix sizes and types to be aliased in
their short forms in a default header regardless of template or Clang matrix
support as well as enabling the templated type declarations.

### Mangling

Mangling of Clang matrices is supported for Itanium but not Microsoft-style
mangling.
Since they shouldn't be mixed, mangling can be shared between Clang and HLSL
matrix types.
Microsoft-style mangling will have to be defined.
Clang vectors have Microsoft mangling support, but it doesn't seem to be
formalized.

Matrices get converted to vectors. In spite of that, they should not
be compatible with overloads that use vectors of the same size
This is a difference from DXC which would accept a 2x2 matrix
to a function that expects a 4-component vector.

### Matrix Row/Column Major Orders

TBD

## Acknowledgments

Florian Hahn (https://github.com/fhahn) for creating the Clang matrix extension!

<!-- {% endraw %} -->
