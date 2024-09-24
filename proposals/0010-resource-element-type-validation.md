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

The proposed solution is to use some type_traits defined in the std library, create
some custom builtins to use as type_traits, and join them together to define a 
set of conceptual constraints for any RET that is used. These conceptual constraints
will be applied to every typed buffer resource type that is defined, so that all
typed buffer HLSL resources have the same rules about which RETs are valid. 
Validation will occur upon resource type instantiation. Additionally, certain 
resource types are raw buffer variants, such as `StructuredBuffer`. These resource 
types will have a different set of type-traits applied, which will loosen constraints
on viable RETs. The type traits will be validated as `concepts`, which is a feature 
introduced in C++20 to statically validate a type.

## Detailed design

In `clang\lib\Sema\HLSLExternalSemaSource.cpp`, `RWBuffer` is defined, along with 
`RasterizerOrderedBuffer` and `StructuredBuffer`. It is at this point that the 
`type_traits` should be incorporated into these resource declarations. A concept 
containing the relevant `type_traits` will be applied to each resource declaration,
and there wil be sufficient context to determine the target IR.
If DXIL is given, then all of the typed buffer `type_traits` will be applied on each
typed buffer HLSL resource type. Otherwise, the raw buffer type_traits will be 
applied to each resource type. If a `type_trait` is not true for the given 
RET, a corresponding error message will be emitted.

The list of type_traits that will be available for use are described below:
| type_trait | Description|
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
at most 4, and the total size in bytes is at most 16. However, type_traits are not
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

// diagnostic: "resource element type 'b' has incomplete definition"
RWBuffer<b> r7; // invalid - the RET isn't complete, the definition is missing. 
// the type_trait that would catch this is `__is_complete_type`

// diagnostic: "resource element type 'c' has non-homogenous aggregate type"
RWBuffer<c> r8; // invalid - struct `oneInt` has int types, and this is not homogenous with the float1 contained in `c`. 
// the type_trait that would catch this is `__builtin_is_homogenous`

StructuredBuffer<c> r8Structured; // valid

// diagnostic: "resource element type 'f' cannot be grouped into 4 32-bit quantities"
RWBuffer<d> r9; // invalid - the struct f cannot be grouped into 4 32-bit quantities.
// no type_trait would catch this, but it would be caught by a concept failure, using the sizeof builtin.

StructuredBuffer<d> r9Structured; // valid

// diagnostic: "resource element type 'RWBuffer<int>' has intangible type"
RWBuffer<RWBuffer<int> > r10; // invalid - the RET has a handle with unknown size, thus it is an intangible RET.
// the type trait that would catch this is `!__is_intangible`
```

Below is a sample implementation of the `RWBuffer` resource type, which is a typed buffer variant.
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

bool is_spirv_target = ...;

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
