<!-- {% raw %} -->

# Target Extension Types for Inline SPIR-V and Decorated Types

* Proposal: [NNNN](NNNN-filename.md)
* Author(s): [Cassandra Beckley](https://github.com/cassiebeckley)
* Status: **Design In Progress**

## Introduction

In this proposal, we define the `spirv.Type` and `spirv.DecoratedType`
target extension types for the SPIR-V backend.

## Motivation

We would like to implement `SpirvType` and `SpirvOpaqueType` from [Inline
SPIR-V (HLSL proposal 0011)](https://github.com/microsoft/hlsl-specs/blob/main/proposals/0011-inline-spirv.md#types)
in the SPIR-V backend. These allow users to create arbitrary `OpType`
instructions, and use them like any other HLSL type. Using these types, a
vendor creating a new extension can expose it to users by creating a header
file without needing to modify the compiler.

Additionally, we need a way to represent types with SPIR-V decorations in LLVM
IR.

## Proposed solution

### SpirvType

To represent `vk::SpirvType` and `vk::SpirvOpaqueType` in LLVM IR, we will add
three new target extension types:

| Type                     | HasZeroInit | CanBeGlobal | CanBeLocal |
|--------------------------|-------------|-------------|------------|
| `spirv.Type`             | - [ ]       | - [x]       | - [x]      |
| `spirv.IntegralConstant` | - [ ]       | - [ ]       | - [ ]      |
| `spirv.Literal`          | - [ ]       | - [ ]       | - [ ]      |

`IntegralConstant` and `Literal` are used to encode arguments to `Type`, and
may not be used outside that context. They are necessary because target
extension types must have all type arguments precede all integer arguments,
whereas SPIR-V type instructions may have an arbitrary number of type,
immediate literal, and constant id operands in any order.

#### `spirv.Type`

```
target("spirv.Type", operands..., opcode, size, alignment)
```

`opcode` is an integer literal representing the opcode of the `OpType`
instruction to be generated. `size` and `alignment` are integer literals
representing the number of bytes a single value of the type occupies and the
power of two that the value will be aligned to in memory. An opaque type can be
represented by setting `size` and `alignment` to zero. `operands` represents a
list of type arguments encoding the operands of the `OpType` instruction. Each
operand must be one of:

* A type argument, which will be lowered to the id of the lowered SPIR-V type
* A `spirv.IntegralConstant`, which will be lowered to the id of an
  `OpConstant` instruction
* A `spirv.Literal`, which will be lowered to an immediate literal value

#### `spirv.IntegralConstant`

```
target("spirv.IntegralConstant", integral_type, value)
```

`integral_type` is the type argument for the `OpConstant` instruction to be
generated, and `value` is its literal integer value.

#### `spirv.Literal`

```
target("spirv.Literal", value)
```

`value` is the literal integer value to be generated.

#### Example

Here's an example of using these types to represent an array of images:

```
%type_2d_image = type target("spirv.Image", float, 1, 2, 0, 0, 1, 0)
%integral_constant_28 = type target("spirv.IntegralConstant", i32, 28)
%integral_constant_4 = type target("spirv.IntegralConstant", i32, 4)
%ArrayTex2D = type target("spirv.Type", %type_2d_image, %integral_constant_4, 28)
```

### Type decorations

In order to represent types with the `vk::ext_decorate`, `vk::ext_decorate_id`,
and `vk::ext_decorate_string` annotations, we will use the
[`int_spv_assign_decoration`](https://github.com/llvm/llvm-project/blob/main/llvm/docs/SPIRVUsage.rst#target-intrinsics)
intrinsic.

<!--
## Detailed design

_The detailed design is not required until the feature is under review._

This section should grow into a full specification that will provide enough
information for someone who isn't the proposal author to implement the feature.
It should also serve as the basis for documentation for the feature. Each
feature will need different levels of detail here, but some common things to
think through are:

* Is there any potential for changed behavior?
* Will this expose new interfaces that will have support burden?
* How will this proposal be tested?
* Does this require additional hardware/software/human resources?
* What documentation should be updated or authored?

## Alternatives considered (Optional)

If alternative solutions were considered, please provide a brief overview. This
section can also be populated based on conversations that occur during
reviewing.

## Acknowledgments (Optional)

Take a moment to acknowledge the contributions of people other than the author
and sponsor.
-->

<!-- {% endraw %} -->
