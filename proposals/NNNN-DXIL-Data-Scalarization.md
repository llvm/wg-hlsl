# DXIL Data Scalarization

* Proposal: [NNNN](NNNN-DXIL-Data-Scalarization.md)
* Author(s): [Farzon Lotfi](https://github.com/farzonl)
* Sponsor: [Farzon Lotfi](https://github.com/farzonl)
* Status: **Under Consideration**

## Introduction

In Proposal [0009](0009-DXIL-Function-Scalarization.md) we covered scalarization
of call instructions, and vector operations like math ops, logical ops,
bitcasts, loads, and stores. The goal of this proposal is to present a solution
for scalarizing data structures via data layout transformations. As a note,
any case that results in an implicit cbuffer will not be covered by this
proposal.

## Motivation

As mentioned in [DXIL.rst](https://github.com/microsoft/DirectXShaderCompiler/blob/main/docs/DXIL.rst#vectors)
"HLSL vectors are scalarized" and "Matrices are lowered to vectors". Therefore,
we need to be able to scalarize these types in clang DirectX backend. Without
scalarizing the data structures and call instructions we can't generate legal
DXIL.

## Background

In DXC we support five forms of data scalarization. data marked with
`groupshared`, `static` function scope, `static` global scope, global data,
and data in function scope. There are then subset behaviors depending on
if we are dealing with arrays of vectors or vectors. The data
scalarization can then be broken down into three cases:

1. `static` scalar layouts
   * vector of `M` size get scalarized into `M` elements.
   * an array of `N` size with a vector of `M` will get scalarized into `M`
     arrays of `N` size.
2. `groupshared` scalar layouts
   * vectors become arrays
   * an array of `N` size with a vector of `M` will lower first to a 2d array
     `N` by `M` and then a 1d.
3. cbuffer usage for regular arrays.

## Proposal

In Proposal [0009](0009-DXIL-Function-Scalarization.md) we introduced the scalarizer
pass this solves all the function scope data scalarization for us. What is left
are the global scope cases. As mentioned in the intro the implicit cbuffer
cases are not in scope for this work. What that leaves us with are the
`groupshared` and `static` cases.

To simplify things for upstream this proposal will make a deviation from `DXC`
and use the same layout transformations for  both `groupshared` and `static`
vectors. Both layouts are legal so this shouldn't cause any problems. The plan
will be to create two new pass. The first pass will convert vectors to arrays
and potentially create multi-dimensional arrays. The second pass will flatten
these arrays into one dimension. These two passes will run successively and
potentially share data about which arrays need to be  flattened via pass
preservation.

While these two pass could have an agnostic order; they will run after the scalarizer
pass. The pass will also only operate on global data since the only cases not
handled by the scalarizer pass are the global scope data cases.
