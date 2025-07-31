<!-- {% raw %} -->

# Resource arrays

* Proposal: [0028](0028-resource-arrays.md)
* Author(s): [Helena Kotas](https://github.com/hekota)
* Status: **Design In Progress**

## Introduction

HLSL Resources are runtime-bound data that are provided as input, output, or
both to shader programs. Shader authors can declare resources as individual
variable declarations or as arrays of resources at local or global scope and
inside user-defined structures.

This document focuses on resource arrays declared at global scope of the shader
or as local variables and function arguments. It includes an analysis what is
currently supported in DXC and a proposal on how to implement that in Clang, and
any potential changes between Clang and DXC. Resources declared inside
user-defined structs will be covered in a separate proposal
([#175](https://github.com/llvm/wg-hlsl/issues/175)).

## Motivation

Resource arrays are fundamental part of the HLSL language. We need to support
them in Clang.

## Current Behavior in DXC

For simplicity the examples below use just the `RWBuffer<float>` resource type,
but same rules apply to other resource types as well.

### Resource Arrays at Global Scope

#### Fixed-size One-dimensional Array

A group of resources can be declared as a one-dimensional array of fixed size:

```
RWBuffer<float> A[4] : register(u10);
```

Each element of the array corresponds to a single resource that is initialized
by an individual `@dx.op.createHandleFromBinding` DXIL intrinsic call. The fact
that this resource is part of an array is encoded in the `dx.types.ResBind`
argument of the call. The `dx.types.ResBind` structure contains binding
information for the whole array - the lower bound and upper bound values for the
register slots and a virtual register space. Third argument of
`@dx.op.createHandleFromBinding` is an index of the individual resource in the
descriptor range from the range `<lower bound, upper bound>` (inclusive).

For example for the resource `A` declared above that is bound to register `u10`,
the DXIL call to initialize resource handle for `A[2]` will have lower bound
value `10`, upper bound `13`, space `0` and array index of `2`:
```
call %dx.types.Handle @dx.op.createHandleFromBinding(i32 217, %dx.types.ResBind { i32 10, i32 13, i32 0, i8 1 }, i32 2, i1 false),
```

Initialization of other resources in the same array would differ only by the
index. The values for upper and lower bound and register space will stay the
same.

https://godbolt.org/z/ff3bnKxov

#### Fixed-size Multi-dimensional Array

Groups of resources can also be declared as multi-dimensional arrays of fixed
size

```
RWBuffer<float> B[4][4] : register(u2);
RWBuffer<float> C[2][2][5] : register(u10, space1);
```

When initializing individual resources of multi-dimensional array the arguments
of `@dx.op.createHandleFromBinding` look like as if the array was flattened to a
single dimension.

That means the array `B[4][4]` is treated as if it was declared as `B[16]`, and
`C[2][2][5]` as if it was `C[20]`.

For example, a call to initialize `C[1][0][3]` from the array declared above
would have lower bound value `10`, upper bound `29`, space `1`, and the index
within the range is `23` = `10 + 1*2*5 + 0*5 + 3`:
```
%dx.types.Handle @dx.op.createHandleFromBinding(i32 217, %dx.types.ResBind { i32 10, i32 29, i32 1, i8 1 }, i32 23, i1 false), 
```

https://godbolt.org/z/8MMWheeGc

#### Arrays of Unbounded Size

Groups of resource arrays can be declared with undefined size. These are called
_unbounded arrays_:
```
RWBuffer<float> D[] : register(u5);
```
For unbounded arrays the `@dx.op.createHandleFromBinding` calls to initialize
individual resource handles will have upper bound set to `-1`. For example an
initialization of handle `D[100]` from the `D` array declared above looks like
this:
```
%dx.types.Handle @dx.op.createHandleFromBinding(i32 217, %dx.types.ResBind { i32 5, i32 -1, i32 0, i8 1 }, i32 105, i1 false)
```
https://godbolt.org/z/hx99s5dzP

#### Unbounded-size Arrays and Multiple Dimensions

For multi-dimensional arrays of resources, only the first dimension can be
unbounded:
```
RWBuffer<float> E[][4] : register(u5);
```
When initializing individual resources of an unbounded multi-dimensional array,
the arguments of `@dx.op.createHandleFromBinding` again look as if the array was
flattened to a single dimension. For example the call to create resource handle
`E[100][3]` from array `E` declared above will have index `408` = `5 + 4 x 100 +
3`:
```
call %dx.types.Handle @dx.op.createHandleFromBinding(i32 217, %dx.types.ResBind { i32 5, i32 -1, i32 0, i8 1 }, i32 408, i1 false),
```
https://godbolt.org/z/YrEnYhrEj

Arrays with unbounded sizes in the other dimensions are not allowed. The error
message DXC reports does not clearly indicate this, though it matches the
diagnostic message produced by Clang for similar case in C++.

```
RWBuffer<float> F[4][];

error: array has incomplete element type 'RWBuffer<float> []'
```
https://godbolt.org/z/osq7dzvdh

### Resource Arrays at Local Scope

#### Local Resource Arrays with Fixed Size

Resources array with fixed size can be declared as local variables in a
function. Resource handles for the individual resources in the array are
uninitialized until they are assigned a value from an initialized resource. DXC
does not report an error when an uninitialized resource is accessed and instead
creates a call to `dx.op.annotateHandle` with zero-initialized handle value (bug
filed:
[microsoft/DirectXShaderCompiler#4415](https://github.com/microsoft/DirectXShaderCompiler/issues/4415)).

```
RWBuffer<float> Buf;
RWBuffer<float> Out;

float foo() {
  RWBuffer<float> LocalArray[3];
  LocalArray[2] = Buf;
  // LocalArray[0] is not initialized
  return LocalArray[2][0] + LocalArray[0][0];
}

[numthreads(4,1,1)]
void main() {
  Out[0] = foo();
}
```
https://godbolt.org/z/Gdc3q674W

#### Unbounded Local Resource Arrays

DXC even allows unbounded resource arrays as local variables in a function. From
a language point of view, this seems very wrong. How is the compiler supposed to
allocate such variables? The fact that DXC allows this should be considered a
bug.

Additionally, and as in the previous example, DXC does not report an error when
an uninitialized resource in an unbounded array is accessed and instead creates
a call to `dx.op.annotateHandle` with zero-initialized handle value.

```
RWBuffer<float> Buf;
RWBuffer<float> Out;

float foo() {
  RWBuffer<float> Unbounded[];
  Unbounded[100] = Buf;
  // Unbounded[0] is not initialized
  return Unbounded[100][0] + Unbounded[0][0];
}

[numthreads(4,1,1)]
void main() {
  Out[0] = foo();
}
```
https://godbolt.org/z/43rGnY4Ee

#### Resource Arrays as Function Arguments

Both fixed-size and unbounded resource arrays can be used as function arguments.
For fixed-size arrays, the dimensions of the array passed into a function must
exactly match the dimensions of the declared argument. For unbounded arrays this
restriction does not exist; a fixed-size array can be used as an argument of a
function that accepts an unbounded array.

```
RWBuffer<float> K[3] : register(u0);
RWBuffer<float> L[2][2] : register(u10);
RWBuffer<float> M[] : register(u0, space1);
RWBuffer<float> Out;

float foo(RWBuffer<float> LK[3], RWBuffer<float> LL[2][2],
          RWBuffer<float> LM1[], RWBuffer<float> LM2[]) {
  return LK[2][0] + LL[1][1][0] + LM1[100][0] + LM2[100][0];
}

[numthreads(4,1,1)]
void main() {
  Out[0] = foo(K, L, M, K);
}
```
https://godbolt.org/z/6Eh3fnME9

Note that array `K` of size `3` is passed into function `foo` via an unbounded
array argument and it is indexed beyond its size.

#### Subsets of Multi-Dimensional Arrays
 
A multi-dimensional array can be indexed to refer to a lower-dimensional subset
of the array. For example, for `RWBuffer<float> N[10][5];` the expression `N[7]`
refers to a sub-array in `N` of size `5`.

```
RWBuffer<float> N[10][5] : register(u0);
RWBuffer<float> Out;

float foo(RWBuffer<float> P[5]) {
  return P[3][0];
}

[numthreads(4,1,1)]
void main() {
  Out[0] = foo(N[7]);
}
```

https://godbolt.org/z/5cG8xWWa6

Note that while the function argument `RWBuffer<float> P[5]` is a local array of
size `5`, it actually refers to a subset of a larger multi-dimensional array
`N`. The handle initialization call for resources in `P` must contain
information about the original array's range.

For example, the handle initialization for the resource that is referenced by `P[3]`
will have lower bound `0`, upper bound `49`, and index `38 = 0 + 7*5 + 3`:

```
call %dx.types.Handle @dx.op.createHandleFromBinding(i32 217, %dx.types.ResBind { i32 0, i32 49, i32 0, i8 1 }, i32 38, i1 false)
```
https://godbolt.org/z/YejsdsTKc

At the same time, `P` is a local variable and as such it is editable. It should
be initialized by copy-in array semantics to refer to resource handles from the
original larger array `N`, but its individual resource handles can be
overridden, and that must not affect the global array `N` or the resources it
contains in any way.

#### Example where DXC Does Not Handle Local Arrays Correctly

Handling of local arrays in DXC is notoriously buggy. For example, in the
following case the shader should write `1` to `Y` and `2` to `X`, but instead
both writes go to `Y`, so the end result is that `X` is unused and is optimized
away.

```
RWBuffer<int> X : register(u0);
RWBuffer<int> Y : register(u1);

void SomeFn(RWBuffer<int> Arr[2], uint Idx, int Val0) {
  Arr[0] = Y;
  Arr[0][Idx] = Val0;
}

[numthreads(4,1,1)]
void main(uint GI : SV_GroupIndex) {
  RWBuffer<int> Arr[2] = {X, Y};
  SomeFn(Arr, GI, 1);
  Arr[0][GI] = 2;
}
```
https://godbolt.org/z/YxM5M6zqo

A brief inspection of the DXC code generation and optimization pipeline shows
that DXC allows Clang to handle resource arrays as if they were regular arrays
of objects until after the LLVM optimization phase. Once all functions have been
inlined in the generated code, DXC locates all references to resource arrays and
replaces them with calls to initialize the resource handle.

The bug in the above example stems from an intentional (but incorrect) decision
not to create a local copy of the resource array argument. If a copy had been
made, the result would likely be correct. However, in some cases, this approach
may still fail to correctly map resource accesses to the bound resource globals
if the code becomes too complex.

#### Resource Arrays in User-defined Structs

Resources and resource arrays can also be included in user-defined structs which
can be declared at local or global scope. While this feature will be covered by
a separate proposal (issues [#175](https://github.com/llvm/wg-hlsl/issues/175)
and [#212](https://github.com/llvm/wg-hlsl/issues/212)), one example is included
here for completeness:

```
struct S {
  int a;
  RWBuffer<float> P[5];
};

S s : register(u10);

cbuffer CB {
    S s_array[4];
};

RWBuffer<float> Out;

[numthreads(4,1,1)]
void main() {
  Out[0] = s.P[2][0] + s_array[1].P[4][0];
}
```
https://godbolt.org/z/Y8h3cWMov

In DXC, when a user-defined struct contains an array of resources, each element
of the array is treated as an individual standalone resource instance. For
`s.P[2]` in the example above the compiler creates a resource named `s.P.2`
mapped to register `u12` with range `1`. Its handle initialization does not
reflect that it is part of a larger array - the upper bound, lower bound and
index values are all the same (`12`):

```
 call %dx.types.Handle @dx.op.createHandleFromBinding(i32 217, %dx.types.ResBind { i32 12, i32 12, i32 0, i8 1 }, i32 12, i1 false)
 ```

Similarly for `s_array[1].P[4]` the compiler creates a resource named
`s_array.1.P.4` with size `1` and implicitly maps it to register `u1`. Handle
initialization again does not include range `5` of the original array:

```
call %dx.types.Handle @dx.op.createHandleFromBinding(i32 217, %dx.types.ResBind { i32 1, i32 1, i32 0, i8 1 }, i32 1, i1 false)
```

## Proposed solution

To avoid issues described
[above](#example-where-dxc-does-not-handle-local-arrays-correctly), we should
aim to resolve initialization of resource array handles early in Clang. That
involves intercepting the codegen on array access to emit a resource class
constructor call, which will eventually be transformed to a
`@dx.op.createHandleFromBinding` DXIL intrinsic. Creating local copies of
resource arrays should be mostly handled by the existing array parameter passing
code, though additional work will likely be needed to support indexing of
subsets of multi-dimensional arrays.

### Changes from DXC

One notable difference from DXC behavior proposed for Clang is related to
handling of unbounded resource arrays:

*Local declarations of unbounded resource arrays will not be allowed.*

https://github.com/microsoft/hlsl-specs/issues/141

Locally-scoped unbounded resource arrays (also called _unsized arrays_) are
incorrect from a language perspective, as are unbounded arrays used as function
arguments. Local array arguments are initialized by creating a local copy of the
array, which does not make sense for arrays of unknown size.

Unbounded resource array declarations will only be allowed at global scope and
can only be referenced through a global variable.

## Detailed design

### Codegen for Resource Array Indexing

We need to intercept codegen for `ArraySubscriptExpr` in Clang codegen. If the
indexed array is a resource array declared at global scope and the expected
result is a single resource, the array element access should be translated to a
resource class constructor call with the appropriate indexing and binding
values.

For example in this simple shader:

```
RWBuffer<float> A[4] : register(u10);
RWStructuredBuffer<float> Out;

[numthreads(4,1,1)]
void main() {
  Out[0] = A[2][1];
}
```

The code generated for the `A[2][1]` expression should be equivalent to
`RWBuffer<float>(10, 0, 4, 2, "A")[1]` - that is, a constructor call followed by a
subscript operator invoked on the resource class. Note that the constructor
arguments represent the resource binding register `10`, space `0`, size of the
array `4`, index in the resource array `2`, and the resource name.

Unlike individual resource declarations, resource arrays at a global scope will
not be initialized by Sema. However, Sema must ensure that the constructor for
the specific resource template class is instantiated and its definition is
emitted, so that Clang codegen can call it.

### Codegen Changes to Handle Local Resource Arrays

Local copies of resource arrays should be mostly handled by the existing code
that creates copies of arrays for function arguments, and by the presence of
copy constructors on resource classes. Some additional work will likely be
required to support indexing of sub-arrays of multi-dimensional resource arrays.

Consider this example:

```
RWBuffer<float> N[10][5] : register(u0);
RWBuffer<float> Out;

float foo(RWBuffer<float> P[5]) {
  return P[3][0];
}

[numthreads(4,1,1)]
void main() {
  Out[0] = foo(N[7]);
}
```

The `N[7]` expression should create a local copy of the sub-array of size `5`.
The changes needed to support this will most likely be required in the same part
of Clang code generation that handles `ArraySubscriptExpr`.

### Changes Needed in LLVM Passes

After Clang code generation and LLVM optimizations, the generated code related
to resource arrays will likely require additional work in LLVM backend passes.

For example, the existing `DXILForwardHandleAccesses` pass aims to eliminate
redundant stores and loads from resource handle globals. However, it currently
expects resource handles to be loaded from a global variable, which is not the
case for resource array element handles.

Additionally, local resource arrays and their copies tend to generate IR code
that includes resource handles stored in local variables (using `alloca` and
lifetime markers), with `load` and `store` operations on those handles through
 an `i32` type. These will need to be either cleaned up in the
 `DXILForwardHandleAccesses` pass, or changes may need to be made to Clang
 codegen for array copying or to subsequent LLVM array optimizations to
 eliminate these unwanted constructs. The scope of this work is currently TBD.
 
## Alternatives Considered

### Resolving Resource Array Indexing in LLVM Pass

Following the DXC approach, leaving resource array handle resolution until after
optimization, to be performed in a dedicated LLVM pass. We would like to avoid
this because this can get very complicated very fast. The DXC pass that handles
this is notoriously buggy (see example
[here](#example-where-dxc-does-not-handle-local-arrays-correctly)).

### Use Builtin Template Class to Represent Resource Arrays

Another approach considered was to encapsulate resource arrays in a built-in
template class defined in `HLSLExternalSemaSource`. The class could be named
`BoundResourceRange` to emphasize that it represents a set of resources
mapped/bound to a descriptor range, rather than a traditional array. The
template arguments would specify the array size and the resource type it
contains. Any resource array variable declaration at global scope would have its
type replaced with the corresponding `BoundResourceRange` specialization.

The class would provide a subscript operator (`[]`) that initializes individual
resource handles as they are accessed. It would support unbounded arrays, and
multi-dimensional arrays could be represented by nesting `BoundResourceRange`

Introducing such a class raises several new questions:
- Should it be directly spellable by users?
- Should users have the option to use either syntax?
- Should we allow explicit `BoundResourceRange` function arguments?
- Does the rewriter need to preserve the original array declaration syntax, or
  is it acceptable to replace resource arrays with `BoundResourceRange`?
- Handling of resources arrays in Sema would need to support both
  `BoundResourceRange` and resource arrays types.
- Creating a local copy of a multi-dimensional array cannot be implemented by the
  class alone and would require changes in Clang code generation anyway.

## Acknowledgments

Chris Bieneman
Justin Bogner
Tex Riddell

<!-- {% endraw %} -->
