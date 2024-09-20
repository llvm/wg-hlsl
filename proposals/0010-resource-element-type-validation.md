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
There are two types of buffers, RawBuffers and TypedBuffers. `RWBuffer`
is a TypedBuffer variant, and `StructuredBuffer` is a RawBuffer variant.
There is a distinct set of rules that define valid RETs for RawBuffer types, 
and a separate set of rules that define valid RETs for `StructuredBuffer` types.
These rules also depend on the target IR, SPIR-V or DXIL.

RETs for TypedBuffer variants may include:
* basic types: 
  * 16- and 32-bit int and uint
  * half and float
* vectors and matrices 
  * containing 4 elements or fewer
  * total size may not exceed 128 bits
* user defined types (structs / classes), as long as:
  * all fields in the struct have the same type
  * there are at most 4 sub elements
  * total size may not exceed 128 bits

RETs for RawBuffer variants are much less constrained:
* it must be a complete type
* cannot contain a handle or resource type

Resource types are never allowed as RETs (i.e., `RWBuffer<int>` as an RET).
Texture resources conform to the rules for TypedBuffers.
If the target is SPIR-V, then only the set of rules for RawBuffers apply. TypedBuffers
like `StructuredBuffer` may have RETs that exceed 128 bits, for example, if the target 
IR is SPIR-V. The TypedBuffer rules above are only enforced when the IR target is DXIL.

If someone writes `RWBuffer<MyCustomType>` and MyCustomType is not a 
valid RET, there should be infrastructure to reject this RET and emit a message 
explaining why it was rejected as an RET.

## Motivation
Currently, there is an allow list of valid RETs. It must be modified with respect 
to this spec. Anything that is not an int, uint, nor a floating-point type, or vectors 
or matrices containing the aforementioned types, will be rejected. The allow list isn't
broad enough, because it doesn't include the case where the RET is user-defined. 
Ideally, a user should be able to determine how any user-defined structure is invalid 
as an RET. Some system should be in place to more completely enforce the rules for 
valid and invalid RETs, as well as provide useful information on why they are invalid.

For example, when targeting DXIL IR, `RWBuffer<double4> b : register(u4);` will emit
an error in DXC, but will not in clang-dxc, despite the fact that `double4` is an 
invalid RET for TypedBuffers.

## Proposed solution

The proposed solution is to use some type_traits defined in the std library, create
some custom builtins to use as type_traits, and join them together to define a 
set of conceptual constraints for any RET that is used. These conceptual constraints
will be applied to every TypedBuffer resource type that is defined, so that all
TypedBuffer HLSL resources have the same rules about which RETs are valid. 
Validation will occur upon resource type instantiation. Additionally, certain 
resource types are RawBuffer variants, such as `StructuredBuffer`. These
resource types will have a different set of type-traits applied, which will
loosen constraints on viable RETs.

## Detailed design

In `clang\lib\Sema\HLSLExternalSemaSource.cpp`, `RWBuffer` is defined, along with 
`RasterizerOrderedBuffer` and `StructuredBuffer`. It is at this point that the 
`type_traits` should be incorporated into these resource declarations. The 
preprocessor will take responsibility for selecting the right set of type_traits
to check, depending on the target IR. If DXIL is given, then all of the TypedBuffer
`type_traits` will be applied on each TypedBuffer HLSL resource type. Otherwise, the
RawBuffer type_traits will be applied to each resource type. For every `type_trait`
that is not true for the given RET, an associated error message will be emitted.

The list of type_traits that will be available for use are described below:
| type_trait | Description|
|-|-|
| `__is_complete_type` | An RET should either be a complete type, or a user defined type that has been completely defined. |
| `__is_resource_element_type` | An RET should be an arithmetic type, or a bool, or a vector or matrix or UDT containing such types. |
| `__builtin_is_homogenous` | A TypedBuffer RET with the DXIL IR target should never have two different subelement types. |
| `__builtin_is_contained_in_four_groups_of_thirty_two_bits` | A TypedBuffer RET with the DXIL IR target should not have more than 4 elements, and the total size of the RET may not exceed 128 bits. |

For the SPIR-V IR target, only `__is_complete_type` and `__is_resource_element_type` 
need to be true. When the target IR is DXIL, and the resource is a TypedBuffer variant,
`__builtin_is_homogenous` will be used to ensure homogeneity. It will use 
`BuildFlattenedTypeList` to retrieve a small vector of the subelement types.
From this subvector, the first element will be compared to all elements in the vector,
and any mismatches will return false.
`__builtin_is_contained_in_four_groups_of_thirty_two_bits` will also use 
`BuildFlattenedTypeList` to retrieve a small vector of the subelement types. It will
then check that the vector length is at most 4, and that the total size in bits is
less than 128, and return false otherwise.

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
// the type_trait that would catch this is `__is_contained_in_four_groups_of_thirty_two_bits`

StructuredBuffer<d> r9Structured; // valid

// diagnostic: "resource element type 'RWBuffer<int>' has intangible type"
RWBuffer<RWBuffer<int> > r10; // invalid - the RET has a handle with unknown size, thus it is an intangible RET.
// the type trait that would catch this is `__is_resource_element_type`
```
## Alternatives considered (Optional)
We could instead implement a diagnostic function that checks each of these conceptual constraints in
one place, either in Sema or CodeGen, but this would prevent us from defining a single header where 
all resource information is localized.

## Acknowledgments (Optional)

<!-- {% endraw %} -->
