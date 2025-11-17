---
title: "[NNNN] - SPIR-V Push constants"
params:
  status: Design In Progress
  authors:
    - Keenuts: Nathan Gauër
---

## Introduction

Push Constants are a Vulkan mechanism to pass a small amount of data to the
shaders without creating buffers or modifying bindings.

Usage is as follows:

```hlsl
struct S {
  float3 light_color;
};

[[vk::push_constant]]
S data;

void main() {
  [...]
  do_something(data.light_color)
}
```
## Motivation

This is a core feature of HLSL+Vulkan.

## Proposed Solution

### HLSL - Parsing

``[[vk::push_constant]]`` is a normal attribute in the `vk` namespace, with
no custom parsing.
This attribute is only allowed on global variables. Additional checks like
storage class compatibility is done in sema.

At this stage, we know the attribute can only be attached to a global
variable.

### HLSL - Sema

During sema, compatibility checks between the global variable definition
and the attribute are checked, and the global variable definition is created.

Additional checks are:
- The attribute is only allowed on a global variable with a struct type.
- There can only be one ``[[vk::push_constant]]`` attribute in the shader.
- There can be no VLA in the struct type (or a nested struct type).

DXC allows any storage class to be attached to a push constant. I believe
this is an oversight and we should probably refuse this. As result, the
following rules will apply:

- The variable storage class must be either `auto` or `uniform`.
- The variable can be marked `const`, but is always considered `const`.

### DXIL

This being a Vulkan specific feature, the attribute is ignored when targeting
DXIL. This means the push constant global becomes part of the cbuffer when
building for DXIL.

The attribute being ignored, the variable belong to the cbuffer, meaning no
additional handling is required.

### SPIR-V

The created global variable after parsing has the following characteristics:
  - the global variable will be marked as `const`.
  - the variable address space will be `hlsl_push_constant`.

Codegen will be left almost as-is as we simply load a variable in a different
address space. The layout rule for those struct follows the same rules as
[RW]StructuredBuffers.
What we need to fixup is the cbuffer logic as a global variable with the
HLSLVkPushConstant attribute should not be added to the constant buffer.

The backend will then lower variables into the `hlsl_push_constant` address
space into a `PushConstant` storage class. The rest is similar to any variable
in another address space and should already be handled.

## Draft PR

There is also a draft PR implementing this end-to-end:
 - https://github.com/llvm/llvm-project/pull/166793
