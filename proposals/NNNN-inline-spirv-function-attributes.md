<!-- {% raw %} -->

# Inline SPIR-V function attributes

*   Proposal: [NNNN](NNNN-inline-spirv-function-attributes.md)
*   Author(s): [Steven Perron](https://github.com/s-perron)
*   Status: **Design In Progress**

*During the review process, add the following fields as needed:*

*   PRs: [#NNNN](https://github.com/llvm/llvm-project/pull/NNNN)
*   Issues: [#NNNN](https://github.com/llvm/llvm-project/issues/NNNN)
*   Posts: [LLVM Discourse](https://discourse.llvm.org/)

## Introduction

The inline SPIR-V extension to HLSL allows users to use most SPIR-V features
without a new compiler release. This allows vendors to quickly deploy extensions
without the overhead of upstreaming changes to the main compiler, enabling
faster iteration and hardware support.

One part of inline SPIR-V is a series of attributes that apply to functions, and
they should be implemented in clang.

## Motivation

The inline SPIR-V feature defines 6 attributes that attach to function or
function parameters:

```hlsl
vk::ext_instruction(uint opcode, [string extended_instruction_set])
vk::spvexecutionmode(uint execution_mode, ...)
vk::ext_extension(string extension_name)
vk::ext_capability(uint capability)
vk::ext_reference
vk::ext_literal
```

They enable vendors to enable a new hardware features to be defined in header
file. This reduces technical debt in the compiler by delegating
extension-specific logic to an HLSL header file separate from the compiler. It
also allows faster release of hardware features because users do not have to
wait for a new version of the compiler to be released.

## Proposed solution

The `vk::ext_instruction`, `vk:spvexecutionmode`, `vk::ext_capability`, and
`vk::ext_extension` will become target attributes on the functions to which they
apply. Then the backend can generate the appropriate SPIR-V. Note that
`vk::ext_capability` and `vk::ext_extension` can apply to variables and type
aliases, but that will be part of another proposal. The `vk::literal` attribute
will be turned in to a target attribute on the function parameter.

The `vk::ext_reference` attribute can be handled in Clang but changing the type
in the AST to a reference type. TODO: Need to figure out how address spaces work
with this.

The following table explains which target attribute each HLSL attribute will
correspond to, and how it will be interpreted in the backend.

HLSL Attribute                                                        | Applicable to                                                                 | llvm-ir target attribute                                     | Attribute Description
--------------------------------------------------------------------- | ----------------------------------------------------------------------------- | ------------------------------------------------------------ | ---------------------
`vk::ext_instruction(uint opcode, [string extended_instruction_set])` | Function declarations with no definition.                                     | `"spv.ext_instruction"="<opcode>,<instruction set>"`         | Calls to functions with this attribute are replaced by a single SPIR-V instruction.<br>If `<instruction set>` is the empty string, then it will generate the core SPIR-V instruction with the given opcode.<br>Otherwise, it will create an `OpExtInst` instruction, where the instruction is `<opcode>` in the given instruction set.
`vk::spvexecutionmode(uint execution_mode, ...)`                      | Entry point functions                                                         | `"spv.executionmode"="<mode>:<op>..."`                       | For each execution mode, a separate `OpExecuteMode` instruction is generated with the given operands. The operands are interpreted as literal integers.
`vk::ext_extension(string extension_name)`                            | Applicable to entry point functions and functions with `vk::ext_instruction`. | `"spv.extextension"="<extension name>,<extension name>,..."` | A separate `OpExtension` instruction is added for each extension name. The extension is added to the list of allowed extensions in the SPIR-V backend.
`vk::ext_capability(uint capability)`                                 | Applicable to entry point functions and functions with `vk::ext_instruction`. | `"spv.extcapability"="<capability id>: <capability id>..."`  | A separate `OpCapability` instruction is added for each capability. The capability is added to the list of allowed capabilities in the SPIR-V backend.
`vk::ext_literal`                                                     | Parameters of functions with `vk::ext_instruction`                            | `"spv.literal"`                                              | The parameter is encoded as a literal in the SPIR-V instruction instead of generating an `OpConstant`.
`vk::ext_reference`                                                   | Parameters of functions with `vk::ext_instruction`                            | N/A (handled in Clang)                                       | The parameter's type is modified to a reference type in the Clang AST. (Address space handling needs further investigation.)

## Detailed design

## Alternatives considered (Optional)

<!-- {% endraw %} -->
