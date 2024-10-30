* Proposal: [0010](0010-resource-element-type-validation.md)
* Author(s): [Joshua Batista](https://github.com/bob80905)
* Sponsor: Joshua Batista
* Status: **Under Consideration**
* Impacted Project(s): (LLVM)
* Issues: [#75676](https://github.com/llvm/llvm-project/issues/75676)

## Introduction
Resources are often used in HLSL, with various resource element types.

For example:
```
RWBuffer<float> rwbuf: register(u0);
```
In this code, the element type is `float`, and the resource type is `RWBuffer`.
`RWBuffer`, along with some other buffers and textures, fall under the "typed buffer"
category. Other buffer resources are categorized as "raw buffers". 
Below is a description of resources that are considered "typed buffers" vs "raw buffers".
* typed buffers
  * [RW|RasterizerOrdered]Buffer
  * [Feedback]Texture*
* raw buffers
  * [Append|Consume|RW|RasterizerOrdered]StructuredBuffer
  * [RW]ByteAddressBuffer

There is a distinct set of rules that define valid element types for typed buffer resources
and valid element types for raw buffer resources.

Element types for typed buffer resources:
* Are not intangible (e.g., isn't a resource type)
* Must be vectors or scalars of arithmetic types, not bools nor enums nor arrays
* Should be a scalar or homogenous vector of a floating-point or integer type, with a maximum of 4 components after translating 64-bit components into pairs of uint32_t components
Element types for raw buffer resources:
* Are not intangible (e.g., isn't a resource type)
* All constituent types must be arithmetic types or bools or enums

Resource types are never allowed as element types (i.e., `RWBuffer<int>` as an element type).
If someone writes `RWBuffer<MyCustomType>` and MyCustomType is not a valid element type, 
there should be infrastructure to reject this element type and emit a message explaining 
why it was rejected as an element type.

## Motivation
Currently, there is an allow list of valid element types where element types not on the list
are rejected. It must be modified with respect to this spec. The allow list isn't
broad enough, because user-defined types aren't allowed for raw buffer resources.
Ideally, a user should be able to determine exactly how any user-defined type is invalid 
as an element type. Some system should be in place to more completely enforce the rules for 
valid and invalid element types, as well as provide useful information on why they are invalid.

For example, `RWBuffer<double4> b : register(u4);` will emit an error in DXC, but will not in 
clang-dxc, despite the fact that `double4` is an invalid element type for typed buffers.

## Proposed solution

The proposed solution is to modify the declaration of each resource declared in 
`clang\lib\Sema\HLSLExternalSemaSource.cpp` and insert into each representative
AST node a concept. The AST node will be created as if the C++20 `concept` keyword
was parsed and applied to the declaration. The concept will be used to validate the
given element type, and will emit errors when the given element type is invalid. 
Although concepts are not currently supported in HLSL, we expect support to be 
added at some point in the future. Meanwhile, because LLVM does support concepts, 
we can make use of them when constructing the AST in Sema.

Two builtins will be used to validate typed buffer element types. Any resource 
element type may not be intangible, so the negation of `__builtin_hlsl_is_intangible`
will be used for both typed and raw buffer resources.
A new built-in, `__builtin_hlsl_typed_element_compatible`, will be added in order
to fully express the typed buffer constraint. This builtin will be placed within a
concept constraint expression that is added to each AST node representing a typed
buffer resource. The builtin is described below. Standard clang diagnostics for
unsatisfied constraints will be used to report any invalid element types. Until 
concepts are formally supported by HLSL, the concepts and constraints will be 
expressed only in the AST via the HLSL external sema source.

## Detailed design

In `clang\lib\Sema\HLSLExternalSemaSource.cpp`, `RWBuffer` is defined, along with 
`RasterizerOrderedBuffer` and `StructuredBuffer`. It is at this point that the 
concept would be incorporated into these resource declarations. A concept representing
the relevant constraints will be applied to each resource declaration. If a concept
is not true for the given element type, a corresponding error message will be emitted.

The list of builtins to be used as type traits that will be available for
concept definition are described below:
| type trait | Description|
|-|-|
| `!__builtin_hlsl_is_intangible ` | An element type should be an arithmetic type, bool, enum, or a vector or matrix or UDT containing such types. This is equivalent to validating that the element type is not intangible. This will error when given an incomplete type. |
| `__builtin_hlsl_typed_element_compatible ` | A typed buffer element type should never have two different subelement types. Compatible typed buffer element types require at most 4 elements, and a total size of at most 16 bytes. The builtin will also disallow the element type if any of its constituent types are enums or bools. |

For typed buffers, `__builtin_hlsl_typed_element_compatible` and 
`!__builtin_hlsl_is_intangible` needs to be true, while `!__builtin_hlsl_is_intangible` is all
that's needed to validate element types for raw buffers. 

### Examples of Element Type validation results:
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

RWBuffer<double2> r0; // valid - element type fits in 4 32-bit quantities
RWBuffer<int> r1; // valid
RWBuffer<float> r2; // valid
RWBuffer<float4> r3; // valid
RWBuffer<notComplete> r4; // invalid - the element type isn't complete, the definition is missing. 
// the type trait that would catch this is the negation of `__builtin_hlsl_is_intangible`
RWBuffer<oneInt> r5; // valid - all leaf types are valid primitive types, and homogenous
RWBuffer<oneFloat> r6; // valid
RWBuffer<twoInt> r7; // valid
RWBuffer<threeInts> r8; // valid
RWBuffer<notHomogenous> r9; // invalid, all template type components must have the same type, DXC fails
StructuredBuffer<notHomogenous> r9Structured; // valid
RWBuffer<depthDiff> r10; // invalid, all template type components must have the same type, DXC fails
RWBuffer<EightElements> r11; // invalid, > 4 elements and > 16 bytes, DXC fails 
// This would be caught by __builtin_hlsl_typed_element_compatible
StructuredBuffer<EightElements> r9Structured; // valid
RWBuffer<EightHalves> r12; // invalid, > 4 elements, DXC fails
// This would be caught by __builtin_hlsl_typed_element_compatible
StructuredBuffer<EightHalves> r12Structured; // valid
RWBuffer<oneIntWithVec> r13; // valid
RWBuffer<weirdStruct> r14; // valid
RWBuffer<RWBuffer<int> > r15; // invalid - the element type has a handle with unknown size, 
// thus it is an intangible element type. The type trait that would catch this is the negation of `__builtin_hlsl_is_intangible`
```

Below is a sample C++ implementation of the `RWBuffer` resource type.
This code would exist within an hlsl header, but concepts are not implemented in HLSL. Instead, the AST node
associated with RWBuffers is constructed as if this code was read and parsed by the compiler.
```
#include <type_traits>

namespace hlsl {

template<typename T>
concept is_typed_element_compatible = 
    __builtin_hlsl_typed_element_compatible(T);

template<typename element_type> requires !__builtin_hlsl_is_intangible(element_type) && is_typed_element_compatible<element_type>
struct RWBuffer {
    element_type Val;
};

// doesn't need __builtin_hlsl_typed_element_compatible, because this is a raw buffer
// also, raw buffers allow bools and enums as constituent types
template<typename T> requires !__builtin_hlsl_is_intangible(T)
struct StructuredBuffer {
    T Val;
};
}

```

## Alternatives considered (Optional)
We could instead implement a diagnostic function that checks each of these conceptual constraints in
one place, either in Sema or CodeGen, but this would prevent us from defining a single header where 
all resource information is localized.

Another alternative considered was creating a builtin called `__builtin_hlsl_is_valid_resource_element_type`, to
check all possible valid resource element types, rather than just checking that the element type is not intangible.
This is unneeded because all primitive non-intangible types are valid element types.

## Acknowledgments (Optional)
* Damyan Pepper
* Chris Bieneman
* Greg Roth
* Sarah Spall
* Tex Riddell
* Justin Bogner
<!-- {% endraw %} -->
