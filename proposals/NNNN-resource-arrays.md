<!-- {% raw %} -->

# Resource arrays

* Proposal: [NNNN](NNNN-resource-arrays.md)
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

For example, a call to initialize `C[1][0][3][0]` from the array declared above
would have lower bound value `10`, upper bound `29`, space `1`, and array index
`23` = `10 + 1*2*5 + 0*5 + 3`:
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
the arguments of `@dx.op.createHandleFromBinding` again look as if the
array was flattened to a single dimension. For example the call to create
resource handle `E[100][3]` from array `E` declared above will have index `408`
= `5 + 4 x 100 + 3`:
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
allocate such variable? The fact that DXC allows this should be considered a bug.

Additionally, and as in the previous example, DXC does not report an error when an
uninitialized resource in an unbounded array is accessed and instead creates a
call to `dx.op.annotateHandle` with zero-initialized handle value.

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
https://godbolt.org/z/W8fx7MnWK

Note that array `K` of size `3` is passed into function `foo` via an unbounded
array argument and it is indexed beyond its size.

#### Subsets of Multi-Dimensional Arrays
 
Multi-dimensional array can be indexed to refer to a lower-dimensional subset of
the array. For example, for `RWBuffer<float> N[10][5];` the expression `N[7]`
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
original larger array `N`, but its individual array elements can be overridden,
and that must not affect the global array `N` or the resources it contains in
any way.

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

This process quickly becomes complex because local arrays are moved using
`memcpy`, and since they are editable, correctly resolving all resource array
accesses is not always straightforward. Given this, the incorrect behavior in
the above example is not surprising.

#### Resource Arrays in User-defined Structs

Resources and resource arrays can also be included in user-defined structs which
can be declared at local or global scope. While this feature will covered by a
separate proposal (issues [#175](https://github.com/llvm/wg-hlsl/issues/175) and
[#212](https://github.com/llvm/wg-hlsl/issues/212)), one example is included
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
of the array is treated as individual standalone resource instance. For `s.P[2]`
in the example above the compiler creates a resource named `s.P.2` mapped to
register `u12` with range `1`. Its handle initialization does not reflect that
it is part of a larger array - the upper bound, lower bound and index values are
all the same (`12`):

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
aim to resolve initialization of resource array handles early in Clang. One
approach is to encapsulate resource arrays in a class that handles the
initialization of individual resource handles when they are accessed.

The class could be named `BoundResourceRange` to emphasize that it represents a
set of resources mapped/bound to a descriptor range, rather than a traditional
array.

The `BoundResourceRange` class would be a built-in template defined in
`HLSLExternalSemaSource`, taking two parameters: the resource type and the
number of elements in the array. In Sema, all global-scope variable declarations
that define a resource array would have their type replaced with the
corresponding `BoundResourceRange` specialization.

For example:

```
RWBuffer<float> A[10] : register(u1);
```

would be equivalent to

```
BoundResourceRange<RWBuffer<float, 10>> A : register(u1);
```

Only resource classes or other `BoundResourceRange` types could be used as the
type parameter for the `BoundResourceRange` template. This restriction would be
enforced using a template concept.

Nested `BoundResourceRange` types will represent multi-dimensional resource
arrays.

For example:

```
RWBuffer<float> B[10][5] : register(u0, space1);
```

would be represented by

```
BoundResourceRange<BoundResourceRange<RWBuffer<float, 5>, 10> B : register(u0, space1);
```

The class would provide a subscript operator (`[]`) that returns an initialized
instance of a resource class from the resource range. For multi-dimensional
arrays, the operator would return a `BoundResourceRange` representing the
lower-dimensional resource array.

Passing a `BoundResourceRange` instance to a function that expects a fixed-size
resource array would create a local copy of the array, per HLSL copy-in array
semantics. Each element of the local array would be initialized using the
resource class instance returned by the `BoundResourceRange` subscript operator
(`[]`).

Resource arrays of unknown size, also known as _unbounded arrays_, would be
represented by the `BoundResourceRange` type with a `Size` template argument of
`-1`. Local declarations of unbounded resource arrays will not be allowed.

It is still under consideration whether unbounded resource arrays should be
supported as function arguments. If supported, these could be passed as
`BoundResourceRange` instances marked as `constant inout`.

## Detailed design

### BoundResourceRange Class Declaration

The `BoundResourceRange` template class will be defined in
`HLSLExternalSemaSource` and will take two template parameters:
- `ResourceT` - the type of resource classes in the array, or another `BoundResourceRange`
- `Size` - number of elements in the array

```
template <typename ResourceT, int Size>
requires ...
class BoundResourceRange {
...
};
```

For fixed-size resource arrays, the `Size` parameter will always be greater than
`0`. For unbounded resource arrays, `Size` will be set to `-1`.

`ResourceT` can be a resource class, such as `RWBuffer<int>` or `Texture`. For
multi-dimensional arrays, `ResourceT` will be `BoundResourceRange` representing
the lower-dimensional resource array.

These constrains will be enforced by a template concept that is described in
more detail [here](#concept-restricting-the-template-type-argument).

### BoundResourceRange Constructors

The `BoundResourceRange` class will have 2 constructors: one for explicitly
bound resource ranges and another for implicit binding. Both constructors will
have signatures matching those of the resource classes.

The `BoundResourceRange` will store binding information for the resource range
in its member fields. This information will be used when accessing individual
resources, i.e. when individual resource classes are initialized and returned
from the subscript operator.

Although it may seem that the class needs to store a lot of information to
capture the resource bindings, all of this data is constant and should get
inlined and resolved by the compiler. No `BoundResourceRange` instances should
exist in the final module. All of this infrastructure should be optimized away,
leaving only the appropriate `llvm.dx.resource.handlefrombinding` and
`llvm.dx.resource.handlefromimplicitbinding` calls with the right values.

```
template <typename ResourceT, unsigned Size>
class BoundResourceRange {
private:
    bool hasImplicitBinding;
    unsigned registerNo; // explicit binding register
    unsigned spaceNo;
    int range;
    unsigned startIndex;
    unsigned implicitBindingOrderID; //  order_id used for implicit binding
    const char *name; // name of the resource array

public:
    // constructor for explicit binding
    BoundResourceRange(unsigned registerNo, unsigned spaceNo, int range,
                  unsigned startIndex, const char *name)
                : hasImplicitBinding(false), registerNo(registerNo),
                spaceNo(spaceNo), range(range), startIndex(startIndex),
                implicitBindingOrderID(unsigned(-1)), name(name) {}

    // constructor for implicit binding
    BoundResourceRange(unsigned spaceNo, int range, unsigned startIndex,
                  unsigned orderId, const char *name)
                : hasImplicitBinding(true), registerNo((unsigned)-1),
                spaceNo(spaceNo), range(range), startIndex(startIndex),
                implicitBindingOrderID(orderId), name(name) {}
...
};
```

The `startIndex` argument indicates which part the resource range the class
represents. For a `BoundResourceRange` class representing full one-dimensional
resource array, this will be `0`. For `BoundResourceRange` instances
representing lower-dimensional subsets of multi-dimensional arrays, `startIndex`
specifies where the subset begins within the original range.

This is important because initializing resource handles from a multi-dimensional
array requires knowledge of the original range size, while a specific
`BoundResourceRange` may only represent a subset starting at `startIndex` with a
length determined by `Size`. The following section explains how `startIndex` is
used in resource index calculations.

### Subscript Operator

The `BoundResourceRange` class will provide a subscript operator (`[]`). For
one-dimensional arrays, it will return an initialized instance of a resource
class from the range. For multi-dimensional arrays, the operator will return a
`BoundResourceRange` representing the lower-dimensional resource array.

```
template <typename ResourceT, unsigned Size>
class BoundResourceRange {
  ...
  ResourceT operator[](unsigned index) {
    unsigned rangeIndex = startIndex + index * ResourceT::GetRequiredBindingSize();
    if (hasImplicitBinding)
      return ResourceT(spaceNo, range, rangeIndex, implicitBindingOrderID, name);
    else
      return ResourceT(registerNo, spaceNo, range, rangeIndex, name);
  }
  ...
};
```

The subscript operator will use a static method `GetRequiredBindingSize`
(described below) to determine the binding size required for each array element.

Because the constructor signature of `BoundResourceRange` matches that of the
resource classes, implementing the subscript operator is greatly simplified.

### GetRequiredBindingSize Method

To correctly compute the range index, the subscript operator must know how many
register slots each element of the array requires. For a `BoundResourceRange`
representing a one-dimensional resource array, this is straightforward — each
resource uses exactly one register slot.

However, for multi-dimensional arrays, the number of required slots per element
can vary as the array element can be another array. To address this, all
resource classes and the `BoundResourceRange` class will implement a static
`GetRequiredBindingSize()` method which returns the number of register slots
needed for each array element.

```
template <typename ResourceT, unsigned Size>
class BoundResourceRange {
  ...
  static unsigned GetRequiredBindingSize() {
    if (Size == -1)
      return -1;
    return Size * ResourceT::GetRequiredBindingSize();
  }
  ...
};

template <typename element_type>
class RWBuffer {
  ...
  static unsigned GetRequiredBindingSize() { return 1; }
  ...
};
```

### Converting to Local Array

Passing a `BoundResourceRange` instance to a function that expects a fixed-size
resource array will create a local copy of the array. Each element of the local
array will be initialized using the resource class instance returned by the
`BoundResourceRange` subscript operator (`[]`). This applies to
multi-dimensional arrays as well, they must be fully copied into the local array
instance.

Originally, it seemed this could be achieved using a conversion operator, such as:

```
template <typename ResourceT, unsigned Size>
class BoundResourceRange {
  ...
  typedef ResourceT ResourceTArray[Size];
  operator ResourceTArray() {
    ResourceT tmp[Size];
    [unroll]
    for (unsigned i = 0; i < Size, i++)
      tmp[i] = (*this)[i];
    return tmp;
  }
  ...
};
```

However, this approach does not work for multi-dimensional arrays, since
`BoundResourceRange` instances representing lower-dimensional array subsets must
also be converted to local arrays.

It appears that converting `BoundResourceRange` instances to local arrays would
need to be handled in Clang code generation.

### Concepts Restricting the BoundResourceRange Template Parameters

The value of the `Size` template parameter of `BoundResourceRange` must be
greater than `0`, or equal to `-1`. This requirement will be enforced by the
following concept:
```
template<int N>
concept ValidBoundResourceRangeSize = (N > 0 || N == -1);
```

The `ResourceT` type parameter must have a static `GetRequiredBindingSize`
method that returns `int`. The following concept will be used to enforce this
requirement:

```
template<typename T>
concept HasGetRequiredBindingSize =
requires {
    { T::GetRequiredBindingSize() } -> std::same_as<int>;
};
```

Additionally, the `ResourceT` type parameter must be an intangible type:

```
template<typename ResourceT>
concept IsHLSLIntangibleType = __builtin_hlsl_is_intangible(ResourceT);
```

The complete `BoundResourceRange` class declaration will look like this:
```
template<typename ResourceT, int Size>
requires ValidBoundResourceRangeSize<Size> &&
  IsHLSLIntangibleType<ResourceT> &&
  HasGetRequiredBindingSize<ResourceT>
class BoundResourceRange {
  ...
}
```

### Changes from DXC

- Local declarations of unbounded resource arrays will not be allowed.

- Unbounded resource arrays as function arguments:
  - Should we allow them?
  - If yes, these will accept only other unbounded array instances and will be
    marked as `constant inout`. Using a fixed-size resource array as an argument
    to a function that expects unbounded array will not be allowed.

### Issues found during prototyping

- local vars remnants from array copying
- pass expecting handle loads from global vars complains about load not being
  from a global

### Open questions
- Will users have an option to use either syntax - resource array or
  `BoundResourceRange`? Or should we make it "unspellable"?

- Should we allow explicit `BoundResourceRange` functions arguments?

- Does rewriter need to preserve array declaration syntax or is it ok to replace
  resource arrays with `BoundResourceRange`?

## Alternatives considered (Optional)

- Following the DXC approach, leaving resource array handle resolution until
  after optimization, to be performed in a dedicated LLVM pass.

- Another approach would be to implement the functionality of
  `BoundResourceRange` directly within Clang code generation, without
  introducing an explicit encapsulating class or replacing variable declaration
  types. This would involve associating binding information with individual
  resource array instances — which is straightforward for global-scope
  resources, but may be more complex for resource arrays inside user-defined
  structs — and intercepting array indexing during code generation to emit the
  correct `@dx.op.createHandleFromBinding` calls or handle local array copying.

## Acknowledgments (Optional)

Chris Bieneman
Justin Bogner
Tex Riddell

<!-- {% endraw %} -->
