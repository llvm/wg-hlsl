# SPIR-V Input/Output built-ins

 * Proposal: [NNNN](NNNN-spirv-input-builtin.md)
 * Author(s): [Nathan Gauër](https://github.com/Keenuts)
 * Status: **Design In Progress**

## Introduction

HLSL has semantic input/outputs parameters used to carry information
to and from a shader, e.g: the system semantic `SV_GroupID` or `MY_SEMANTIC`,
a user-defined semantic.

In SPIR-V, those are translated to `Input` and `Output` variables,
with either a `BuiltIn` or `Location` decoration.

Example:

```hlsl
float4 vsmain(float4 Position : POSITION) : SV_POSITION
{
  return Position;
}
```

Both `POSITION` and `SV_POSITION` will be represented as an `OpVariable`:

- `POSITION` will have the `Input` storage class.
- `SV_POSITION` will have the `Output` storage class.

- `POSITION` will be decorated with `Location 0`.
- `SV_POSITION` will be decorated with `BuiltIn Position`.

In addition, users can define their own SPIR-V built-ins using inline SPIR-V:

```hlsl
[[vk::ext_builtin_input(/* NumWorkGroups */ 24)]]
static const uint3 myBuiltIn;
```

This document explain how we plan on implementing those in Clang/LLVM.

## Proposed Solution

## Frontend changes

Global variables marked with Inline SPIR-V will be marked using two new
attributes:
- `HLSLInputBuiltin`
- `HLSLOutputBuiltin`

In addition, a new address space will be added:
- `vulkan_private`

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
- The address space will be set to `vulkan_private`
- a constructor will be added.
- a destructor will be added.

The construction will call a target-specific intrinsic: `spv_load_builtin`.
This builtin takes the SPIR-V built-in ID as parameter, and returns the
value of the corresponding built-in.

The destructor will call another intrinsic: `spv_store_builtin`. This builtin
takes the SPIR-V built-in ID, as well as a value to store as parameter.

And lastly, to support input parameters with semantics, the same intrinsic
will be called in the generated entrypoint wrapper function.

Because the 2 new intrinsics will be marked as `MemWrite` or `MemRead`, LLVM
won't be able to optimize them away, and the initial/final load/store will
be kept.

Corresponding code could be:

```
[[vk::ext_builtin_input(/* GlobalInvocationId */ 28)]]
static const uint3 myBuiltIn;

void main(uint3 thread_id_from_param : SV_DispatchThreadID) {
  [...]
}

constructor_myBuiltIn() {
  myBuiltIn = spv_load_builtin(28);
}

destructor_myBuiltIn() {
  spv_store_builtin(28, myBuiltIn);
}

void entrypoint() {
  constructor_myBuiltIn();

  uint3 input_param1 = spv_load_builtin(28);
  main(input_param1)

  destructor_myBuiltIn();
}
```

The emitted global variable for inline SPIR-V will be in the global scope,
meaning it will require the `Private` storage class in SPIR-V.
Because of that, globals linked to the added attributes will require a new
address space `vulkan_private`.

## Backend changes

Backend will translate the new `vulkan_privatge` address space to
`StorageClass::Private`.

The backend will also need to implement 2 new intrinsics:
```
llvm_any_ty spv_load_builtin(i32 built_in_id);
spv_store_builtin(i32 built_in_id, llvm_any_ty);
```

Both will use the GlobalRegistry to get/create a builtin global variable with
the correct decoration. A call to the `load` will generate an Input builtin,
while a call to the `store` will generate an `Output` builtin.

Only the first lowering of each intrinsic will generate a builtin.

The load intrinsic will then add an `OpLoad`, while the store an `OpStore`.

## Draft PR

https://github.com/llvm/llvm-project/pull/116393



