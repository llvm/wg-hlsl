<!-- {% raw %} -->

# Implementation of Root Signatures in DX Container

* Proposal: [NNNN](NNNN-filename.md)
* Author(s): [Xiang Li](https//github.com/python3kgae), [Damyan
  Pepper](https://github.com/damyanp), [Joao Saffran](https://github.com/joaosaffran)
* Status: **Design In Progress**

<!--
*During the review process, add the following fields as needed:*

* PRs: [#NNNN](https://github.com/microsoft/DirectXShaderCompiler/pull/NNNN)
* Issues:
  [#NNNN](https://github.com/microsoft/DirectXShaderCompiler/issues/NNNN)
  -->

## Introduction

[Purposal 0002](https://github.com/joaosaffran/wg-hlsl/blob/purposal/root-signatures/proposals/0002-root-signature-in-clang.md?plain=1)
adds root signature into LLVM IR. The remaining support to generated DXContainer 
in a binary serialized format need to be added into clang.

This change proposes adding:

* Conversion of the metadata representation to the binary serialized format.
* Testing solutions to validate root signature blob generation within DX Container.

## Motivation

The motivation is the same as the one in [Proposal 0002](0002-root-signature-in-clang.md#motivation).

## Proposed solution
### Generating of Root Signature blob

During backend code generation, the LLVM IR metadata representation of the root
signature is converted to data structures that are more closely aligned to the
final file format. For example, root parameters and static samplers can be
intermingled in the previous formats, but are now separated into separate arrays
at this point.

Example:

```c++
RootSignature[
 "RootFlags(ALLOW_INPUT_ASSEMBLER_INPUT_LAYOUT),"
 "CBV(b0, space=1),"
 "StaticSampler(s1),"
 "DescriptorTable("
 "  SRV(t0, numDescriptors=unbounded),"
 "  UAV(u5, space=1, numDescriptors=10))"
]
```

Suggested Datastructure representation for the example above:

```c++
rootSignature = RootSignature(
  ALLOW_INPUT_ASSEMBLER_INPUT_LAYOUT,
  { // parameters
    RootCBV(0, 1),
    DescriptorTable({
      SRV(0, 0, unbounded, 0),
      UAV(5, 1, 10, 0)
    })
  },
  { // static samplers
    StaticSampler(1, 0)
  });
```

At this point, validation is performed to ensure that the root signature
itself is valid. One key validation here is to check that each register is only
bound once in the root signature. Even though this validation has been performed
in the Clang frontend, we also need to support scenarios where the IR comes from
other frontends, so the validation must be performed here as well.

Once the root signature itself has been validated, validation is performed
against the shader to ensure that any registers that the shader uses are bound
in the root signature. This validation needs to occur after any dead-code
elimation has completed.

### Validations

The validations must be the same as [Purposal 0002](https://github.com/joaosaffran/wg-hlsl/blob/main/proposals/0002-root-signature-in-clang.md#validations-in-sema),
the main difference here is that those are not syntactic checks, and should
instead verify the actual binary values are within range.

### Testing

Testing DX Container generation requires a two stage testing strategy.

1. Use Google Test unit tests to create and inspect binary files for specific
   hex values, this is useful for local validation.
2. Cyclic tests, generating YAML from the binary, and then check the other
   way as well.

Some examples are the existing DX Container unit tests. 

Such test infrastructure will require the design and construction of a disassembler
for Root Signature Blob or DX Container.

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

<!-- {% endraw %} -->
