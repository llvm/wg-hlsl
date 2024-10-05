* Proposal: [0010](0010-resource-element-type-validation.md)
* Author(s): [Joshua Batista](https://github.com/bob80905)
* Sponsor: Joshua Batista
* Status: **Under Consideration**
* Impacted Project(s): (LLVM)
* Issues: [#75676](https://github.com/llvm/llvm-project/issues/75676)

## Introduction
Resources are often used in HLSL, with various resource element types (RETs).

For example:
```
RWBuffer<float> rwbuf: register(u0);
```
In this code, the RET is `float`, and the resource type is `RWBuffer`.
All resources can be placed in two categories, raw buffers and typed buffers. 
Below is a description of all resources and their corresponding categories
* raw buffers
  * [Append|Consume|RW]StructuredBuffer
  * [RW]ByteAddressBuffer
* typed buffers
  * [RW]Buffer
  * [Feedback]Texture*

There is a distinct set of rules that define valid RETs for raw buffer resources, 
and a separate set of rules that define valid RETs for typed buffer resources.

RETs for typed buffer resources:
* Are not intangible (e.g., isn't a resource type)
* Must be vectors or scalars of arithmetic types, not bools nor enums nor arrays
* The type should be line-vector layout compatible (homogenous, at most 4 elements, and at most 128 bits in size) 

RETs for raw buffer variants are much less constrained:
* Are not intangible (e.g., isn't a resource type)
* All constituent types must be arithmetic types or bools or enums

Resource types are never allowed as RETs (i.e., `RWBuffer<int>` as an RET).
If someone writes `RWBuffer<MyCustomType>` and MyCustomType is not a 
valid RET, there should be infrastructure to reject this RET and emit a message 
explaining why it was rejected as an RET.

## Motivation
Currently, there is an allow list of valid RETs. It must be modified with respect 
to this spec. Anything that is not a valid RET will be rejected. The allow list isn't
broad enough, because there is no case where the RET is user-defined for a raw buffer.
Ideally, a user should be able to determine how any user-defined structure is invalid 
as an RET. Some system should be in place to more completely enforce the rules for 
valid and invalid RETs, as well as provide useful information on why they are invalid.

For example, when targeting DXIL IR, `RWBuffer<double4> b : register(u4);` will emit
an error in DXC, but will not in clang-dxc, despite the fact that `double4` is an 
invalid RET for typed buffers.

## Proposed solution

The proposed solution is to modify the declaration of each resource declared in 
`clang\lib\Sema\HLSLExternalSemaSource.cpp` and insert into each representative
AST node a concept. The AST node will be created as if the C++20 `concept` keyword
was parsed and applied to the declaration. The concept will be used to validate the
given RET, and will emit errors when the given RET is invalid. Although concepts are
not currently supported in HLSL, we expect support to be added at some point in the
future. Meanwhile, because LLVM does support concepts, we can make use of
them when constructing the AST in Sema.

A new built-in, `__builtin_hlsl_is_line_vector_layout_compatible`, will be 
added in order to express the extra typed buffer constraint. This builtin
will be added to each AST node that requires that constraint. The builtin is 
described below.Standard clang diagnostics for unsatisfied constraints will be 
used to report any invalid element types. Concepts required will differ depending
on whether the resource is a typed buffer or a raw buffer. Until concepts are 
formally supported by HLSL, the concepts and constraints will be expressed 
directly in the AST via the HLSL external sema source.

## Detailed design

In `clang\lib\Sema\HLSLExternalSemaSource.cpp`, `RWBuffer` is defined, along with 
`RasterizerOrderedBuffer` and `StructuredBuffer`. It is at this point that the 
concept would be incorporated into these resource declarations. A concept representing
the relevant constraints will be applied to each resource declaration. If a concept
is not true for the given RET, a corresponding error message will be emitted.

The list of builtins to be used as type traits that will be available for
concept definition are described below:
| type trait | Description|
|-|-|
| `__is_intangible` | An RET should be an arithmetic type, bool, enum, or a vector or matrix or UDT containing such types. This is equivalent to validating that the RET is not intangible. This will error when given an incomplete type. |
| `__builtin_hlsl_is_line_vector_layout_compatible` | A typed buffer RET with the DXIL IR target should never have two different subelement types. Line vector layout compatible also requires at most 4 elements, and a total size of at most 16 bytes. |

For raw buffers, only `!__is_intangible` needs to be true. 
For typed buffers, `__builtin_hlsl_is_line_vector_layout_compatible` 
also needs to be true. This builtin will be used to ensure homogeneity. 
It will use `BuildFlattenedTypeList` to retrieve a small vector of the subelement types.
From this subvector, the first element will be compared to all elements in the vector,
and any mismatches will return false. Typed buffer RETs will 
also need to have at most 4 subelements, and the total size in bytes cannot exceed 16,
which will also be verified by `__builtin_hlsl_is_line_vector_layout_compatible`.
Finally, there will be an additional check that there are no bools or enums present
in any component of the type.

### Examples of RET validation results:
```
struct oneInt {
    int i;
};

struct twoInt {
   int aa;
   int ab;
};

struct threeInts {
  oneInt o;
  twoInt t;
};

struct oneFloat {
    float f;
};
struct notComplete;
struct depthDiff {
  int i;
  oneInt o;
  oneFloat f;
};

struct notHomogenous{     
  int i;
  float f;
};

struct EightElements {
  twoInt x[2];
  twoInt y[2];
};

struct EightHalves {
half x[8]; 
};

struct intVec {
  int2 i;
};

struct oneIntWithVec {
  int i;
  oneInt i2;
  int2 i3;
};

struct weirdStruct {
  int i;
  intVec iv;
};

RWBuffer<double2> r0; // valid - RET fits in 4 32-bit quantities
RWBuffer<int> r1; // valid
RWBuffer<float> r2; // valid
RWBuffer<float4> r3; // valid
RWBuffer<notComplete> r4; // invalid - the RET isn't complete, the definition is missing. 
// the type trait that would catch this is the negation of `__is_intangible`
RWBuffer<oneInt> r5; // valid - all leaf types are valid primitive types, and homogenous
RWBuffer<oneFloat> r6; // valid
RWBuffer<twoInt> r7; // valid
RWBuffer<threeInts> r8; // valid
RWBuffer<notHomogenous> r9; // invalid, all template type components must have the same type, DXC fails
StructuredBuffer<notHomogenous> r9Structured; // valid
RWBuffer<depthDiff> r10; // invalid, all template type components must have the same type, DXC fails
RWBuffer<EightElements> r11; // invalid, > 4 elements and > 16 bytes, DXC fails 
// This would be caught by __builtin_hlsl_is_line_vector_layout_compatible
StructuredBuffer<EightElements> r9Structured; // valid
RWBuffer<EightHalves> r12; // invalid, > 4 elements, DXC fails
// This would be caught by __builtin_hlsl_is_line_vector_layout_compatible
StructuredBuffer<EightHalves> r12Structured; // valid
RWBuffer<oneIntWithVec> r13; // valid
RWBuffer<weirdStruct> r14; // valid
RWBuffer<RWBuffer<int> > r15; // invalid - the RET has a handle with unknown size, thus it is an intangible RET.
// the type trait that would catch this is the negation of `__is_intangible`
```

Below is a sample C++ implementation of the `RWBuffer` resource type, which is a typed buffer variant.
This code would exist within an hlsl header, but concepts are not implemented in HLSL. Instead, the AST node
associated with RWBuffers is constructed as if this code was read and parsed by the compiler.
```
#include <type_traits>

namespace hlsl {

template<typename RET>
concept TypedResourceElementType = 
    __builtin_hlsl_is_line_vector_layout_compatible<RET>() &&
    !std::is_enum_v<RET> && !std::is_same_v<RET, bool>;

template<typename T> requires !__is_intangible(T) && TypedResourceElementType<T>
struct RWBuffer {
    T Val;
};

// doesn't need __builtin_hlsl_is_line_vector_layout_compatible, because this is a raw buffer
// also, raw buffers allow bools and enums as constituent types
template<typename T> requires !__is_intangible(T)
struct StructuredBuffer {
    T Val;
};
}

```

## Alternatives considered (Optional)
We could instead implement a diagnostic function that checks each of these conceptual constraints in
one place, either in Sema or CodeGen, but this would prevent us from defining a single header where 
all resource information is localized.

Another alternative considered was creating a builtin called `__is_valid_resource_element_type`, to
check all possible valid resource element types, rather than just checking that the RET is not intangible.
This is unneeded because all primitive non-intangible types are valid RETs.

## Acknowledgments (Optional)
* Damyan Pepper
* Chris Bieneman
* Greg Roth
* Sarah Spall
* Tex Riddell
* Justin Bogner
<!-- {% endraw %} -->
