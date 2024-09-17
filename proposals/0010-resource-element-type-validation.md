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
In this code, the RET is `float`, and the resource type is `RWBuffer`. The
resource type is not a `RawBuffer` variant, and so there is a distinct set
of rules that define valid RETs for this resource type.

RETs for non-`RawBuffer` variants may include basic types (ints and uints of sizes 16
and 32, as well as half, float, vectors, and matrices of 4 elements or fewer).
Structs that contain fields of these basic types (where all fields in the struct have
the same type) may also be RETs. 
Structs that either have structs as fields or arrays of structs as fields may also be
allowed, as long as there are at most 4 sub elements, and each sub element is at most
32 bits. Additionally, resource types are not allowed within an RET, even if the 
underlying resource type has a primitive RET (i.e., `RWBuffer<int>` as an RET).

RETs for `RawBuffer` variants are much less constrained, the only rule is that the RET
may not be an incomplete type (a handle type or a resource type).

If someone writes `RWBuffer<MyCustomType>` and MyCustomType is not a 
valid RET, there there should be infrastructure to reject this RET and emit a message 
explaining why it was rejected as an RET.

## Motivation
Currently, there is an allow list of valid RETs. It must be modified with respect 
to this spec. Anything that is not an int, uint, nor a floating-point type, or vectors 
or matrices containing the aforementioned types, will be rejected. The allow list isn't
broad enough, because it doesn't include the case where the RET is user-defined. 
Ideally, a user should be able to determine how any user-defined structure is invalid 
as an RET. Some system should be in place to more completely enforce the rules for 
valid and invalid RETs, as well as provide useful information on why they are invalid.

For example, `RWBuffer<double4> b : register(u4);` will emit an error in DXC, 
but will not in clang-dxc, despite the fact that `double4` is an invalid RET.

## Proposed solution

The proposed solution is to use some type_traits defined in the std library, create
some custom type_traits that aren't defined there, and join them together to define a 
set of conceptual constraints for any RET that is used. These conceptual constraints
will be applied to every non-`RawBuffer` resource type that is defined, so that all
non-`RawBuffer` HLSL resources have the same rules about which RETs are valid. 
Validation will occur upon resource type instantiation. Additionally, certain 
resource types are `RawBuffer` variants, such as `StructuredBuffer`. Such resource 
types will have a `[[hlsl::raw_buffer]]` attribute in the attributed type. These
resource types will also have a different set of type-traits applied, which will
loosen constraints on viable RETs. Specifically, `__is_homogenous` and 
`__is_at_most_four_elements_and_at_most_thirty_two_bits_each` will be missing from this set.

## Detailed design

In `clang\lib\Sema\HLSLExternalSemaSource.cpp`, `RWBuffer` is defined, along with 
`RasterizerOrderedBuffer` and `StructuredBuffer`. It is at this point that the 
`type_traits` should be incorporated into these resource declarations. All of the
non-`RawBuffer` `type_traits` will be applied on each non-`RawBuffer` HLSL resource
type. For every `type_trait` that is not true for the given RET, an associated error
message will be emitted. 

The list of type_traits that define a valid non-`RawBuffer` RET are described below:
| type_trait | Description|
|-|-|
| `__is_complete_type` | An RET should either be a complete type, or a user defined type that has been completely defined. |
| `__is_intangible_type` | An RET should not contain any handles with unknown sizes, i.e., should not be intangible. So, we should assert this type_trait is false. |
| `__is_homogenous` | RETs may be basic types (including vector or matrix), but if they are aggregate types, then all underlying basic types should be the same type. |
| `__is_at_most_four_elements_and_at_most_thirty_two_bits_each` | RETs should not have more than 4 elements, and each element may not exceed 32 bits in size. |

Only `__is_complete_type` and `__is_intangible_type` are needed for `RawBuffer` RETs.

* Examples:
```
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
RWBuffer<b> r7;// invalid - the RET isn't complete, the definition is missing. 
// the type_trait that would catch this is `__is_complete_type`

// diagnostic: "resource element type 'c' has non-homogenous aggregate type"
RWBuffer<c> r8; // invalid - struct `oneInt` has int types, and this is not homogenous with the float1 contained in `c`. 
// the type_trait that would catch this is `__is_homogenous`

StructuredBuffer<c> r8Structured; // valid

// diagnostic: "resource element type 'f' cannot be grouped into 4 32-bit quantities"
RWBuffer<d> r9; // invalid - the struct f cannot be grouped into 4 32-bit quantities.
// the type_trait that would catch this is `__is_at_most_four_elements_and_at_most_thirty_two_bits_each`

StructuredBuffer<d> r9Structured; // valid

// diagnostic: "resource element type 'RWBuffer<int>' has intangible type"
RWBuffer<RWBuffer<int> > r10; // invalid - the RET has a handle with unknown size, thus it is an intangible RET.
// the type trait that would catch this is `__is_intangible_type`
```
## Alternatives considered (Optional)
We could instead implement a diagnostic function that checks each of these conceptual constraints in
one place, either in Sema or CodeGen, but this would prevent us from defining a single header where 
all resource information is localized.

## Acknowledgments (Optional)

<!-- {% endraw %} -->
