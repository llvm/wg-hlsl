# Global symbol visibility

*   Proposal: [NNNN](http://NNNN-filename.md)
*   Author(s): [Steven Perron](https://github.com/s-perron)
*   Status: **Design In Progress**

*During the review process, add the following fields as needed:*

*   PRs: [\#NNNN](https://github.com/llvm/llvm-project/pull/NNNN)
*   Issues: [\#NNNN](https://github.com/llvm/llvm-project/issues/NNNN)
*   Posts: [LLVM Discourse](https://discourse.llvm.org/)

## Introduction

Section 3.6 of the
[HLSL specification](https://microsoft.github.io/hlsl-specs/specs/hlsl.pdf)
defined the possible linkages for names. This proposal updates how these
linkages are represented in LLVM IR. The current implementation presents
challenges for the SPIR-V backend due to inconsistencies with OpenCL. We propose
that names with program linkage in HLSL should have external linkage and default
visibility in LLVM IR, while names with external linkage in HLSL should have
external linkage and hidden visibility in LLVM IR.

## Motivation

Consider the following HLSL snippet:

```
void external_linkage() { … }
export void program_linkage() { … }
```

In llvm-ir, these function will be represented as:

```
define void @external_linkage()() local_unnamed_addr #0 !dbg !8 {
  ret void, !dbg !12
}

define void @program_linkage()() local_unnamed_addr #1 !dbg !13 {
  ret void, !dbg !14
}

attributes #0 = { ... } # no hlsl.export
attributes #1 = { ... "hlsl.export" ...}
```

In the DirectX backend, there is a pass that will “finalize” the linkage. It
will change `@external_linkage’s` linkage to internal, and remove the
`hlsl.export` attribute from `@program_linkage`.

The SPIR-V backend emits the `Export` linkage attribute for every symbol with
external linkage. For the example above, `external_linkage` would be decorated
with the `Export` linkage attribute giving it the equivalent of program linkage.
We cannot change this without modifying the behaviour for OpenCL. OpenCL
generates functions that look exactly like `external_linkage` and they require
the `Export` linkage attribute in the SPIR-V.

To be consistent with OpenCL, we must represent function with program linkage
the way we currently represent functions with `external_linkage`. Then we can
represent functions with external linkage as with some other attribute.

## Proposed solution

I propose mapping HLSL concepts found in section 3.6 of the HLSL specification
as follows:

HLSL concept                        | LLVM-IR concept
:---------------------------------- | :---------------
Translation unit                    | Translation unit
Program (partially or fully linked) | Shared library

Then, we can map the HLSL linkages to LLVM IR as follows:

| HLSL Linkage                                                                                                   | LLVM-IR representation                                                                                                                                                                                                                                   |
|----------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Program linkage**:<br> Visible outside the program                                                           | **Linkage type: external**<br> **Visibility style: default**<br> These symbols are potentially visible outside the shared library.                                                                                                                       |
| **External linkage**:<br> These symbols are visible outside the translation unit, but not outside the program. | **Linkage type: external**<br> **Visibility style: hidden**<br> These symbols are visible outside the translation unit and therefore participate in linking. However, the hidden visibility style means they are not visible outside the shared library. |
| **Internal linkage**:<br> Visible anywhere in the translation unit, but not outside it.                        | **Linkage type: internal**<br> **Visibility style: default**<br> These symbols are accessible in the current translation unit but will be renamed to avoid collisions during linking. That is, they are not visible outside the translation unit.        |


See the LLVM language reference for definitions of the
[linkage types](https://llvm.org/docs/LangRef.html) and
[visibility styles](https://llvm.org/docs/LangRef.html).

This provides a clean conceptual mapping from HLSL to LLVM IR and will be
consistent with OpenCL’s implementation.

Backends should assume they are generating HLSL programs. If any linking occurs,
it happens before the backend.
