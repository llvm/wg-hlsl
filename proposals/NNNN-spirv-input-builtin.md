# SPIR-V Input/Output built-ins

 * Proposal: [NNNN](NNNN-spirv-input-builtin.md)
 * Author(s): [Nathan Gauër](https://github.com/Keenuts)
 * Status: **Design In Progress**

## Introduction

HLSL has semantic input/outputs parameters used to carry information
to and from a shader, e.g: the system semantic `SV_GroupID` or `MY_SEMANTIC`,
a user-defined semantic.

In SPIR-V, those are translated to `Input` and `Output` variables,
with either a `BuiltIn` or `Location` decoration. This proposal only
focuses the `BuiltIn` interface variables.

Input `BuiltIn` values are private to the executing lane. Reading their
value has no side-effect. If not used, those built-in can safely be removed
from the shader module.

Output 'BuiltIn' values are slightly different:
 - Their initial value is undefined. Loading them is UB.
 - Storing to it has a side effect: removing the pipeline default value.
 - Loading the built-in once stored to is defined: it returns the last
   set value.

Examples:
```hlsl
  float a = my_output_builtin * 123.f; // Undefined behavior.
  my_output_builtin = my_output_builtin; // Undefined behavior.
  my_output_builtin = 0.f; // Replacing pipeline's default value with 0.f.
  float b = my_output_builtin; // Defined, b = 0.f;
```

In HLSL, Input/Output built-ins can be accessed through two methods:

```hlsl
[[vk::ext_builtin_input(/* NumWorkGroups */ 24)]]
static const uint3 from_a_global;

void main(uint3 from_a_semantic : SV_ThreadId)
{
  uint3 a = from_a_semantic + from_a_global;
}
```

This document explain how we plan on implementing those in Clang/LLVM.

## Proposed Solution

## Frontend changes

Global variables marked with `vk::ext_builtin_input` or
`vk::ext_builtin_output` will be marked in the AST using two new attributes:
- `HLSLInputBuiltin`
- `HLSLOutputBuiltin`

In addition, a two new address spaces will be added:
- `hlsl_input`
- `hlsl_output`

The TD file will attach each attribute to a `SubjectList` with the following
constraints:

```
HLSLInputBuiltin:  S->hasGlobalStorage() &&
                   S->getStorageClass()==StorageClass::SC_Static &&
                   S->getType().isConstQualified()

HLSLOutputBuiltin: S->hasGlobalStorage() &&
                   S->getStorageClass()==StorageClass::SC_Static &&
                   !S->getType().isConstQualified()

def HLSLVkExtBuiltinInput: InheritableAttr {
  let Spellings = [CXX11<"vk", "ext_builtin_input">];
  let Args = [IntArgument<"BuiltIn">];
  let Subjects = SubjectList<[HLSLInputBuiltin], ErrorDiag>;
  let LangOpts = [HLSL];
}

def HLSLVkExtBuiltinOutput: InheritableAttr {
  let Spellings = [CXX11<"vk", "ext_builtin_output">];
  let Args = [IntArgument<"BuiltIn">];
  let Subjects = SubjectList<[HLSLOutputBuiltin], ErrorDiag>;
  let LangOpts = [HLSL];
}
```

When this attribute is encountered, several changes will occur:
- Address space will be set to `hlsl_input` for input built-ins.
- Address space will be set to `hlsl_output` for output built-ins.
- a `spirv.Decoration` metadata is added with the `BuiltIn <id>` decoration.

The address space change will allow the back-end to correctly determine the variable
storage class.
The metadata will be converted to `OpDecorate <reg> BuiltIn <id>`.


The same mechanism will be used for semantic inputs, but we'll also create
load/stores in the entry-point wrapper to be equivalent to:

```
[[vk::ext_builtin_input(/* GlobalInvocationId */ 28)]]
static const uint3 dispatch_thread_id;

[[vk::ext_builtin_output(/* ValidOutputSemantic */ 1234)]]
static uint3 output_semantic;

[numthreads(1, 1, 1)]
uint3 csmain(uint3 id : SV_DispatchThreadID) : SV_SomeValidOutputSemantic {
  [...]
}

void generated_entrypoint() {
  output_semantic = main(dispatch_thread_id);
}
```

If the entrypoint returns a struct with semantic on fields, the entrypoint
wrapper will have 1 store per semantic, and the module 1 global per semantic.

## Backend changes

The SPIR-V backend will translate the new `hlsl_input` address space to
`StorageClass::Input`, and `hlsl_output` to `StorageClass::Output`.

The SPIR-V backend already accepts the `spirv.Decoration` metadata.
No change is required for the entrypoint wrapper.

# FAQ

## Why not follow the DXIL design with load/store functions?

SPIR-V implements built-ins as variables.
Storing to an output built-in has a hidden side-effect on the pipeline.
Implementing this as a global variable is the most natural way to implement
this. Implementing it like DXIL using functions would require tracking those,
and only generating the input/output variable if at least one read/write is
valid.
