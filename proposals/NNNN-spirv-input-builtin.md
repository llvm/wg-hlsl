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

Input `BuiltIn` values are private to the executing lane. Reading their
value has no side-effect. If not used, those built-in can safely be removed
from the shader module (Unlike the inputs tagged with `Location`).

Output 'BuiltIn' values starts with an undefined value. Those are private
to the lane, and storing to them had no other side-effect than to modify the
initially stored value. It is allowed to load those values.

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
- a constructor will be added for both input & output builtins.
- a destructor will be added to output builtins.

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

[[vk::ext_builtin_output(/* SomeUnknownOutput */ 1234)]]
static uint3 myOutputBuiltIn;

void main(uint3 thread_id_from_param : SV_DispatchThreadID) {
  [...]
}

constructor_myBuiltIn() {
  myBuiltIn = spv_load_builtin(28);
}

constructor_myOutputBuiltIn() {
  myOutputBuiltIn = spv_load_builtin(1234);
}

destructor_myOutputBuiltIn() {
  spv_store_builtin(1234, myOutputBuiltIn);
}

void entrypoint() {
  constructor_myBuiltIn();
  constructor_myOutputBuiltIn();

  uint3 input_param1 = spv_load_builtin(28);
  main(input_param1)

  destructor_myOutputBuiltIn();
}
```

The emitted global variable for inline SPIR-V will be in the global scope,
meaning it will require the `Private` storage class in SPIR-V.
Because of that, globals linked to the added attributes will require a new
address space `vulkan_private`.

## What about unused or conditionally loaded Input built-ins?

Loading a built-in has no side-effect. Hence, the load can be duplicated, or
hoisted in the entry function/global ctor.

If the variable is loaded, and result is never used, LLVM should be able to
optimize those loads away. Same goes for the remaining unused local variable.

## What about conditionally stored Output built-ins?

Output built-ins starts with an undefined value. This means if the shader
doesn't modify this builtin, we should either remove it, or leave it
unchanged.

The simplest option is to load the initial value, and then allow the shader
to modify it.

The global value ctor would load the builtin value into the global, and the
global dtor store it back.
From the SPIR-V point of view, loading then storing this undefined value
should not have any impact, as builtin load/stores should not have
side-effects.

This design at least allows us to have correct code, even if the output
builtin modification is gated behing a condition:
 - lanes taking this branch would modify the undefined into a known value.
 - lanes not taking this branch would load & store back the undefined value.

# What about unused Output built-ins?

The issue the ctor/dtor approach has is it prevents LLVM to eliminate unused
output built-ins.

Assuming we correctly run `dce`, `always-inline`, `dse`, `deadargelim` passes,
we should end up with an unoptimized `spv_load_builtin()` and
`spv_store_builtin()`.

Because those are marked `MemRead` and `MemWrite`, LLVM won't be able to
optimize them away.

Solving could probably be done using a custom IR pass:
- this would consider a given BuiltIn ID to represent a location in memory.
- hence, it could associate the load/store pairs.
- if the loaded value remains unchanged when passed to a store, eliminate
  both.

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



