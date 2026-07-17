<!-- {% raw %} -->

# Representing SpirvType in Clang's Type System

- Proposal: [NNNN](NNNN-spirv-types-in-clang.md)
- Author(s): [Cassandra Beckley](https://github.com/cassiebeckley)
- Status: **Design In Progress**

## Introduction

We are implementing `SpirvType` and `SpirvOpaqueType` defined in
[Inline SPIR-V (HLSL proposal 0011)](https://github.com/microsoft/hlsl-specs/blob/main/proposals/0011-inline-spirv.md#types).
In order to support this feature, we need a way to represent inline SPIR-V types
in the Clang type system. To facilitate this, I am proposing
`HLSLInlineSpirvType` as a new `Type` subclass, and `__hlsl_spirv_type` as a new
builtin template to create such a type.

## Motivation

In DXC, we represented `SpirvType` as a template for a struct. This was simple
to implement, since in DXC we lower the AST directly to SPIR-V without going
through LLVM codegen, and could add special cases handling structs that were
`SpirvType` specializations while lowering types. However, this approach does
not interact well with Sema and the rest of Clang, resulting in several bugs in
handling template arguments and other areas. In order to take the same approach
in Clang, we would need to add special case handling while lowering struct
types, as well as for calculating size and alignment and anywhere else structs
are interacted with in Clang. Struct types are already processed separately from
all other types while lowering, and adding special cases for `SpirvType` would
complicate their handling even more.

Finally, a struct is not a good semantic representation of a `SpirvType`.
`SpirvType` is fundamentally a new kind of type for Clang that is different from
all existing types—it represents a low-level target type specified by the user.
This type is opaque and cannot be represented as a struct because Clang does not
treat structs as opaque.

## Proposed solution

### Type Representation

`HLSLInlineSpirvType` is a subclass of `clang::Type`, which has the properties

| Property    | Description                                                                                              | Optional | Type                   |
| ----------- | -------------------------------------------------------------------------------------------------------- | -------- | ---------------------- |
| `Opcode`    | [SPIR-V opcode enumerant](https://registry.khronos.org/SPIR-V/specs/unified1/SPIRV.html#_instructions_3) | no       | `uint32_t`             |
| `Size`      | Number of bytes a single value of the type occupies                                                      | yes      | `uint32_t`             |
| `Alignment` | A power of two that the value will be aligned to in memory                                               | yes      | `uint32_t`             |
| `Operands`  | List of arguments to the SPIR-V type instruction                                                         | no       | array of`SpirvOperand` |

A value of type `HLSLInlineSpirvType` is always canonical.

#### Operands

Each operand in `Operands` is a value of the nested class
`HLSLInlineSpirvType::SpirvOperand`, which can be one of the following kinds:

| Kind         | Description                                                                        | Has Result Type | Has Integral Value |
| ------------ | ---------------------------------------------------------------------------------- | --------------- | ------------------ |
| `ConstantId` | Represents a value to be passed in as the ID of a SPIR-V `OpConstant` instruction. | yes             | yes                |
| `Literal`    | Represents a value to be passed in as an immediate literal.                        | no              | yes                |
| `TypeId`     | Represents a type to be passed in as the ID of a SPIR-V `OpType*` instruction      | yes             | no                 |

### Type Declaration

Since `HLSLInlineSpirvType` types should only be created using the `SpirvType`
and `SpirvOpaqueType` templates, we do not need to provide special syntax for
their declaration. In order to implement these templates, and to avoid the
necessity of creating an additional dependent type, these types will be created
using a `vk::__hlsl_spirv_type` template.

```C++
template <uint32_t Opcode, uint32_t Size, uint32_t Alignment,
          typename... Operands>
using __hlsl_spirv_type = ...;
```

The implementation of this struct, represented above as `...`, will be provided
as a
[Clang builtin type alias](https://clang.llvm.org/docs/LanguageExtensions.html#builtin-type-aliases).
This builtin can then be used to implement `SpirvType` and `SpirvOpaqueType`:

```C++
namespace vk {
    template <uint Opcode, uint Size, uint Alignment, typename... Operands>
    using SpirvType = __hlsl_spirv_type<Opcode, Size, Alignment, Operands...>;

    template <uint Opcode, typename... Operands>
    using SpirvOpaqueType = __hlsl_spirv_type<Opcode, 0, 0, Operands...>;
}
```

Operands will be interpreted as specified in
[Inline SPIR-V](https://github.com/microsoft/hlsl-specs/blob/main/proposals/0011-inline-spirv.md#types).
To specify an opaque type, `Size` and `Alignment` can be set to zero.

<!--
## Detailed design

_The detailed design is not required until the feature is under review._

This section should grow into a full specification that will provide enough
information for someone who isn't the proposal author to implement the feature.
It should also serve as the basis for documentation for the feature. Each
feature will need different levels of detail here, but some common things to
think through are:

- Is there any potential for changed behavior?
- Will this expose new interfaces that will have support burden?
- How will this proposal be tested?
- Does this require additional hardware/software/human resources?
- What documentation should be updated or authored?

## Alternatives considered (Optional)

If alternative solutions were considered, please provide a brief overview. This
section can also be populated based on conversations that occur during
reviewing.

## Acknowledgments (Optional)

Take a moment to acknowledge the contributions of people other than the author
and sponsor.
-->

<!-- {% endraw %} -->
