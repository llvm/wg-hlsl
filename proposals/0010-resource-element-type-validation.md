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
There are two types of buffers, raw buffers and typed buffers. Below is a 
list of all buffers and their corresponding variants
* raw buffers
  * [Append|Consume|RW]StructuredBuffer
  * [RW]ByteAddressBuffer
* typed buffers
  * [RW]Buffer
  * [Feedback]Texture*

There is a distinct set of rules that define valid RETs for raw buffer types, 
and a separate set of rules that define valid RETs for typed buffer types.
These rules also depend on the target IR, SPIR-V or DXIL.

RETs for typed buffer variants with a DXIL target IR may include:
* basic types: 
  * 16, 32, and 64-bit int and uint
  * half, float, and double
* vectors and matrices 
  * containing 4 elements or fewer
  * total size may not exceed 128 bits
* user defined types (structs / classes), as long as:
  * all fields in the struct have the same type
  * there are at most 4 sub elements
  * total size may not exceed 128 bits

RETs for raw buffer variants are much less constrained:
* it must be a complete type
* cannot contain a handle (such as resource types)

Resource types are never allowed as RETs (i.e., `RWBuffer<int>` as an RET).
Texture resources conform to the rules for typed buffers.
If the target is SPIR-V, then only the set of rules for raw buffers apply. Typed buffers
like `RWBuffer` may have RETs that exceed 128 bits, for example, if the target 
IR is SPIR-V. The typed buffer rules above are only enforced when the IR target is DXIL.

If someone writes `RWBuffer<MyCustomType>` and MyCustomType is not a 
valid RET, there should be infrastructure to reject this RET and emit a message 
explaining why it was rejected as an RET.

## Motivation
Currently, there is an allow list of valid RETs. It must be modified with respect 
to this spec. Anything that is not a valid RET will be rejected. The allow list isn't
broad enough, because it doesn't include the case where the RET is user-defined. 
Ideally, a user should be able to determine how any user-defined structure is invalid 
as an RET. Some system should be in place to more completely enforce the rules for 
valid and invalid RETs, as well as provide useful information on why they are invalid.

For example, when targeting DXIL IR, `RWBuffer<double4> b : register(u4);` will emit
an error in DXC, but will not in clang-dxc, despite the fact that `double4` is an 
invalid RET for typed buffers.

## Proposed solution

The proposed solution is to use C++20 concepts to validate the element type.
A new built-in, `__builtin_is_homogenous`, will be added in order to express constraints
that can't currently be expressed in pure HLSL code. Standard clang diagnostics for 
unsatisfied constraints will be used to report any invalid element types. Concepts
required will differ depending on whether the resource is a typed buffer or a raw buffer.
Until concepts are formally supported by HLSL, the concepts and constraints 
will be expressed directly in the AST via the HLSL external sema source.

## Detailed design

In `clang\lib\Sema\HLSLExternalSemaSource.cpp`, `RWBuffer` is defined, along with 
`RasterizerOrderedBuffer` and `StructuredBuffer`. It is at this point that the 
type traits should be incorporated into these resource declarations. A concept 
containing the relevant type traits will be applied to each resource declaration,
and there wil be sufficient context to determine the target IR.
If DXIL is given, then all of the typed buffer type traits will be applied on each
typed buffer HLSL resource type. Otherwise, the raw buffer type traits will be 
applied to each resource type. If a type trait is not true for the given 
RET, a corresponding error message will be emitted.

The list of type traits that will be available for use are described below:
| type trait | Description|
|-|-|
| `__is_complete_type` | An RET should either be a complete type, or a user defined type that has been completely defined. |
| `__is_intangible` | An RET should be an arithmetic type, or a bool, or a vector or matrix or UDT containing such types. This is equivalent to validating that the RET is not intangible. |
| `__builtin_is_homogenous` | A typed buffer RET with the DXIL IR target should never have two different subelement types. |

For the SPIR-V IR target, only `__is_complete_type` and `!__is_intangible` 
need to be true. When the target IR is DXIL, and the resource is a typed buffer variant,
`__builtin_is_homogenous` will be used to ensure homogeneity. 
It will use `BuildFlattenedTypeList` to retrieve a small vector of the subelement types.
From this subvector, the first element will be compared to all elements in the vector,
and any mismatches will return false.
Typed buffer RETs with the DXIL IR target will need have a vector length that is
at most 4, and the total size in bytes is at most 16. However, type traits are not
needed to verify these, since they can be checked directly using template techniques
and the `sizeof` builtin.

* Examples:
```
// targeting DXIL
struct oneInt {
	int i;
};
struct twoInt {
   int aa;
   int ab;
};
struct a {
   oneInt bx;
   int i;
};
struct b;
struct c {
  oneInt ca;
  float1 cb;
};
struct d {
  twoInt x[2];
  twoInt y[2];
};
RWBuffer<double2> r0; // valid - RET fits in 4 32-bit quantities
RWBuffer<int> r1; // valid
RWBuffer<float> r2; // valid
RWBuffer<float4> r3; // valid
RWBuffer<oneInt> r4; // valid
RWBuffer<oneInt> r5; // valid - all fields are valid primitive types
RWBuffer<a> r6; // valid - all leaf types are valid primitive types, and homogenous

RWBuffer<b> r7; // invalid - the RET isn't complete, the definition is missing. 
// the type trait that would catch this is `__is_complete_type`

RWBuffer<c> r8; // invalid - struct `oneInt` has int types, and this is not homogenous with the float1 contained in `c`. 
// the type trait that would catch this is `__builtin_is_homogenous`

StructuredBuffer<c> r8Structured; // valid

RWBuffer<d> r9; // invalid - the struct d exceeds 16 bytes.
// no type trait would catch this, but it would be caught by a concept failure, using the sizeof builtin.

StructuredBuffer<d> r9Structured; // valid

RWBuffer<RWBuffer<int> > r10; // invalid - the RET has a handle with unknown size, thus it is an intangible RET.
// the type trait that would catch this is `!__is_intangible`

struct EightHalves { half x[8] };  // sizeof(EightHalves) == 16
RWBuffer<EightHalves> b; // invalid - EightHalves has 8 subelements, which exceeds the limit of 4.
// This would be caught using a template that extracts the element count of the RET's vector, and comparing against 4.
```

Below is a sample C++ implementation of the `RWBuffer` resource type, which is a typed buffer variant.
This code would exist within `HLSLExternalSemaSource.cpp`, as a substitute for the existing definition
of `RWBuffer`
```
#include <type_traits>

namespace hlsl {

template<typename T>
struct is_vector_type {
  constexpr static bool value = false;
};

template <typename T, unsigned N>
struct is_vector_type<T __attribute__((ext_vector_type(N)))> {
  constexpr static bool value = true;
};

template <typename T>
struct vector_type_info;

template <typename T, unsigned N>
struct vector_type_info<T __attribute__((ext_vector_type(N)))> {
  using Type = T;
  constexpr static unsigned Size = N;
};

const bool is_spirv_target = getASTContext().getTargetInfo().getTriple().isSPIRV();

template<typename T>
concept is_valid_line_vector = sizeof(T) <= 16 && vector_type_info<T>::Size <= 4;
template<typename T>
concept is_valid_vector_RET_for_typed_buffer = is_spirv_target || (is_valid_line_vector<T> && __builtin_is_homogenous(T))

template<typename T> requires (!is_vector_type<T>::value || is_valid_vector_RET_for_typed_buffer<T>)
 && __is_complete_type(T) && !__is_intangible(T)
struct RWBuffer {
    T Val;
};

template<typename T, int N>
using vector = T __attribute__((ext_vector_type(N)));
}

using namespace hlsl;

void fn() {
    RWBuffer<vector<float, 8>> Buf; // failure, caught by is_valid_line_vector being false within is_valid_vector_RET_for_typed_buffer
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
Damyan Pepper
Chris Bieneman
Greg Roth
Sarah Spall
<!-- {% endraw %} -->
