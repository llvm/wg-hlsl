# Representing counter variables for typed buffers

*   Proposal: [NNNN](http://NNNN-typed-buffer-counters.md)
*   Author(s): [Steven Perron](https://github.com/s-perron)
*   Status: **Design In Progress**

## Introduction

In HLSL, RWStructuredBuffer, AppendStructuredBuffer, and ConsumeStructuredBuffer
buffer types have two associated buffers: primary storage (an array of T) and a
32-bit integer counter that can be atomically incremented or decremented.

In DirectX, the counter and main storage share a binding and are closely tied.
However, SPIR-V lacks the flexibility to represent both with a single binding.
Consequently, DXC represents the counter resource as a separate resource with
its own binding, allowing flexible counter allocation at the cost of a separate
set and binding.

We propose that Clang represent typed buffers that may have a counter as a class
with two handles: one for main storage and one for the counter. This makes it
explicit that they are separate resources.

## Motivation

The counter variables are a core feature in HLSL, and must be represented.

## Proposed solution

Access to resources occurs through handles stored in a static global variable.
Currently, RWStructuredBuffer objects contain a single handle for both main
storage and counter access.

We propose that RWStructuredBuffer objects be modified to include two separate
handles: one for main storage (bufferHandle) and one for the counter
(counterHandle). These handles would be initialized independently in the
constructor using separate calls to resource.handlefrombinding.

For DXIL, both handles would share the same type, and the calls to
resource.handlefrombinding will be identical. They could potentially be commoned
by the compiler.

For SPIR-V, the handles would have distinct types as detailed in
[0018-spirv-resource-representation.md](http://0018-spirv-resource-representation.md).
The method for determining the counter variable's binding number is beyond the
scope of this proposal.

## Detailed design

## Alternatives considered (Optional)

### Multiple binding numbers on `resource.handlefrombinding`

One possible solution is to incorporate multiple binding locations into
resource.handlefrombinding. This would allow the SPIR-V backend to expand the
call into multiple resources. However, this solution is not ideal because it
would necessitate the creation of an ad hoc target type within the SPIR-V
backend.

In contrast, the proposed solution only requires a single target type to
represent a generic Vulkan buffer. This type could potentially be reused by any
language targeting Vulkan.

### Including the binding for the counter in the handle type.

The inclusion of the counter's binding number in the type returned by
resource.handlefrombinding was another potential solution. However, this
solution is not feasible due to resource aliases. As an example, it would be
impossible to determine the type for a RWStructuredBuffer function parameter
because it lacks a single binding location.

## Acknowledgments
