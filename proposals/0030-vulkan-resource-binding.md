---
title: "[0030] - Vulkan Resource Binding"
params:
    status: Design In Progress
    authors:
        - s-perron: Steven Perron
---

* Issues: [#124561](https://github.com/llvm/llvm-project/issues/124561)

## Introduction

This proposal outlines a design for translating HLSL resource binding syntax and
rules into the Vulkan binding model. The goal is to enable HLSL code to work
seamlessly across both DirectX and Vulkan, mirroring the functionality provided
by the DirectX Compiler (DXC).

## Motivation

Currently, HLSL's resource binding model is tightly coupled with DirectX. This
poses a significant challenge for developers who want to use HLSL in a Vulkan
environment. To address this, we propose to implement the resource binding
mechanisms available in DXC, allowing users to bind resources in a predictable
manner that is suitable for Vulkan.

## Proposed solution

To support the various use cases for resource binding, we will implement the
core mechanisms found in DXC. This includes support for explicit binding through
the `vk::binding`, `vk::counter_binding`, and `register` attributes, as well as
a system for implicit binding allocation. Command-line options that modify
resource binding assignments will be evaluated for potential deprecation.

The implementation will follow the approach used for DXIL, as detailed in
[0024-implicit-resource-binding.md](0024-implicit-resource-binding.md). Clang
will use two intrinsics to communicate binding information to the SPIR-V
backend:

*   `@llvm.spv.resource.handlefrombinding` for resources with **explicit
    bindings**, where both the descriptor set and binding are known.
*   `@llvm.spv.resource.handlefromimplicitbinding` for resources with **implicit
    bindings**, where only the descriptor set is known. A backend pass will then
    be responsible for assigning a concrete binding.

## Detailed design

### Clang Code Generation

Clang uses two intrinsics to represent resource accesses:

```llvm
@llvm.spv.resource.handlefrombinding(i32 DescSet, i32 Binding, i32 ArraySize, i32 Index, bool isUniformIndex, ptr Name)
@llvm.spv.resource.handlefromimplicitbinding(i32 OrderId, i32 DescSet, i32 ArraySize, i32 Index, bool isUniformIndex, ptr Name)
```

The Clang code generation algorithm is as follows:

1.  If a declaration has the `vk::binding(Binding, DescSet)` attribute, Clang
    assigns an explicit binding with the given set and binding.
2.  If a declaration has the `register(xB, spaceS)` attribute:
    *   Clang assigns the resource to descriptor set `S` (or the default
        descriptor set if `spaceS` is missing).
    *   Clang assigns the resource to binding `B`.
3.  If a declaration has the `register(spaceS)` attribute (without a binding):
    *   Clang assigns the resource to descriptor set `S`.
    *   Clang does not assign a binding; this is an implicit binding.
4.  If a declaration has no `register` or `vk::binding` attribute:
    *   Clang assigns the resource to the default descriptor set.
    *   Clang does not assign a binding; this is an implicit binding.
5.  If a resource has an associated counter buffer, Clang creates a second
    resource handle for it. The binding for the counter buffer is determined as
    follows:
    *   If the resource has the `vk::counter_binding(b)` attribute, Clang
        assigns the counter buffer an explicit binding `b`. The counter buffer
        resides in the same descriptor set as the main resource.
    *   Otherwise, Clang assigns the counter buffer an implicit binding in the
        same descriptor set as the main resource. The `OrderId` for the counter
        buffer is assigned as if it were declared immediately after the
        associated resource, ensuring a predictable order for implicit binding
        allocation.

### Implicit Binding in the SPIR-V Backend

A backend pass will replace all calls to
`@llvm.spv.resource.handlefromimplicitbinding` with calls to
`@llvm.spv.resource.handlefrombinding`. Bindings will be assigned according to
the `OrderId`, where each resource is assigned the first unused binding within
its descriptor set.

## Examples

### Implicit binding example

Consider the following HLSL compute shader where four resources are declared
without explicit bindings:

```hlsl
RWBuffer<float4> A;
RWBuffer<float4> B[4];
RWBuffer<float4> C;
RWBuffer<float4> D;

[numthreads(1, 1, 1)]
void main(uint3 dispatchThreadId : SV_DispatchThreadID)
{
    float4 color = A[0];
    for (int i = 0; i < 4; ++i)
        color += B[i][0];
    D[0] = color + C[0];
}
```

With the proposed changes, Clang will assign implicit bindings to these
resources based on their declaration order in the source code. All four
resources will be placed in the default descriptor set (set 0).

*   `A` is the first resource declared, so it will be assigned binding 0.
*   `B` is declared next, so it will be assigned binding 1. It is an array of
    four buffers, but it will be represented by a single descriptor binding.
*   `C` is the third resource, so it will be assigned the next available
    binding, which is 2.
*   `D` is the last resource, so it will be assigned binding 3.

This behavior is consistent with DXC default behavior when targeting SPIR-V.
However, this differs from the DXIL behavior described in
[0024-implicit-resource-binding.md](0024-implicit-resource-binding.md). In DXIL,
the resource array `B` will take 4 register slots. In SPIR-V, resource arrays
(like `B[4]`) use a single binding.

### Explicit register assignment

Consider the following HLSL compute shader where four resources are declared
with explicit resources:

```hlsl
RWBuffer<float4> A : register(u0);
RWBuffer<float4> B[4] : register(u1, space1);
RWBuffer<float4> C : register(u1);
RWBuffer<float4> D : register(u0, space1);

[numthreads(1, 1, 1)]
void main(uint3 dispatchThreadId : SV_DispatchThreadID)
{
    float4 color = A[0];
    for (int i = 0; i < 4; ++i)
        color += B[i][0];
    D[0] = color + C[0];
}
```

With the proposed changes, Clang will assign bindings to these resources based
on the register assignment in the source code.

*   `A` is assigned binding 0 in the default descriptor set (set 0).
*   `B` is assigned binding 1 in descriptor set 1. It is an array of four
    buffers, but it will be represented by a single descriptor binding.
*   `C` is assigned binding 1 in the default descriptor set (set 0).
*   `D` is assigned binding 0 in descriptor set 1.

This behavior is consistent with DXC's default behavior.

### Explicit Vulkan binding

Consider the following HLSL compute shader where three resources are declared
with explicit Vulkan bindings:

```hlsl
[[vk::binding(2, 1)]] RWBuffer<float4> A;
[[vk::binding(0)]] RWBuffer<float4> B;
[[vk::binding(1, 1)]] RWBuffer<float4> C;

[numthreads(1, 1, 1)]
void main(uint3 dispatchThreadId : SV_DispatchThreadID)
{
    C[0] = A[0] + B[0];
}
```

With the proposed changes, Clang will assign bindings to these resources based
on the `vk::binding` attribute.

*   `A` is assigned binding 2 in descriptor set 1.
*   `B` is assigned binding 0 in the default descriptor set (set 0).
*   `C` is assigned binding 1 in descriptor set 1.

### Mixed explicit bindings

Consider the following HLSL compute shader where a resource is declared with
both a `vk::binding` and a `register` attribute:

```hlsl
[[vk::binding(2, 1)]] RWBuffer<float4> A : register(u0);
[[vk::binding(0)]] RWBuffer<float4> B : register(u1);
[[vk::binding(1, 1)]] RWBuffer<float4> C : register(u2);

[numthreads(1, 1, 1)]
void main(uint3 dispatchThreadId : SV_DispatchThreadID)
{
    C[0] = A[0] + B[0];
}
```

The `vk::binding` attribute takes precedence over the `register` attribute.

*   `A` is assigned binding 2 in descriptor set 1.
*   `B` is assigned binding 0 in the default descriptor set (set 0).
*   `C` is assigned binding 1 in descriptor set 1.

### Space-only register annotations

This example highlights how `register(spaceN)` annotations are handled.

```c++
RWBuffer<float> A : register(u1);        // defaults to space0
RWBuffer<float> B[];                     // gets u2 (unbounded range) in DXIL
RWBuffer<float> C[3] : register(space1); // gets u0, space1 (range 3) in DXIL
RWBuffer<float> D : register(space1);    // gets u3, space1 in DXIL

[numthreads(4,1,1)]
void main() {
  A[0] = C[2][0] + D[0] + B[10][0];
}
```

Under the proposed SPIR-V binding rules, the assignments would be:

*   `A` has an explicit binding: binding 1 in the default descriptor set (set
    0).
*   `B` has an implicit binding. It is the first declared resource with an
    implicit binding in set 0, so it is assigned the first available slot:
    binding 0 in set 0.
*   `C` has an implicit binding in `space1`. It is the first declared resource
    for set 1, so it is assigned binding 0 in set 1.
*   `D` has an implicit binding in `space1`. It is the second declared resource
    for set 1, so it is assigned the next available slot: binding 1 in set 1.

This differs from the DXIL behavior described in
[0024-implicit-resource-binding.md](0024-implicit-resource-binding.md),
particularly for the unbounded array `B` and for `D` which follows a resource
array. In SPIR-V, resource arrays (like `C[3]`) are treated as a single binding,
which simplifies the layout.

### Conflict with explicit register assignment

Consider the following HLSL compute shader where three resources are declared
with conflicting explicit resources:

```hlsl
RWBuffer<float4> A : register(t0);
RWBuffer<float4> B : register(s0);
RWBuffer<float4> C : register(u0);

[numthreads(1, 1, 1)] void main(uint3 dispatchThreadId : SV_DispatchThreadID) {
C[0] = A[0] + B[0]; } ```

With the proposed changes, Clang will assign the same set and binding to all
three resources. All will be in descriptor set 0 at binding 0. This will be an
error because all three resources are used by the shader.

This behavior is consistent with DXC's default behavior. However, if the
`-vk-s-shift=50` option was provided to DXC, the binding for the resource in
register `s0` would be 50, removing the conflict. This option will not be
implemented in Clang. See the open questions.

### Unused resource array

Consider the following HLSL compute shader where a resource array is declared
but not used:

```hlsl
RWBuffer<float4> A;
RWBuffer<float4> B[4];
RWBuffer<float4> C;
RWBuffer<float4> D;

[numthreads(1, 1, 1)]
void main(uint3 dispatchThreadId : SV_DispatchThreadID)
{
    D[0] = A[0] + C[0];
}
```

Because `B` is not used, it will be removed by the optimizer. This means that
the implicit binding assignments will be affected.

*   `A` is the first resource declared, so it will be assigned binding 0.
*   `B` is unused and removed.
*   `C` is the third resource, so it will be assigned the next available
    binding, which is 1.
*   `D` is the last resource, so it will be assigned binding 2.

This behavior is different from DXC's default behavior, which assigns bindings
before optimizations. See the open questions.

### Resources in a struct

Consider the following HLSL compute shader where resources are declared inside a
struct:

```hlsl
RWBuffer<float> A : register(u0);
RWBuffer<float> B : register(u2);

struct S {
  RWBuffer<float> C;
  RWBuffer<float> D;
} s;

[numthreads(4,1,1)]
void main() {
  A[0] = s.D[0] + s.C[0] + B[0];
}
```

This proposal assigns implicit bindings based on declaration order for all
resources, including those within a `struct`. This provides predictable and
stable binding assignments.

*   `A` is explicitly bound to `register(u0)`, so it is assigned binding 0.
*   `B` is explicitly bound to `register(u1)`, so it is assigned binding 2.
*   `s.C` is the first implicitly bound resource declared. It is assigned the
    first available binding, which is binding 1.
*   `s.D` is the second implicitly bound resource. It is assigned the next
    available binding, which is binding 3.

This behavior is different from DXC when targeting SPIR-V, which assigns
bindings for resources in a struct in a contiguous set of binding. Since `s.D
and s.C` cannot both fit between `A` and `B`, then both come after. `s.C` gets
binding 3, and `s.D` gets binding 4. Unlike DXIL, they are assigned binding
based on the order that they are declared in the struct.

The proposed behavior is consistent with the behavior in Clang when targeting
DXIL.

### Resource arrays in a struct

Consider the following HLSL compute shader where resource arrays are declared
inside a struct:

```hlsl
struct S {
    RWBuffer<float> A[4];
    RWBuffer<float> B[2];
    RWBuffer<float> C[3];
};

RWBuffer<float> D : register(u2);
S s;

[numthreads(4,1,1)]
void main() {
  D[0] = s.C[2][0] + s.B[1][0] + s.A[3][0] + s.C[1][0];
}
```

This proposal treats each resource array as a single entity. Each array will be
assigned a single binding, and the bindings will be assigned based on
declaration order.

*   `D` is explicitly bound to `register(u2)`, so binding 2 is reserved.
*   `s.A` is the first implicitly bound resource. It is an array of 4, but it
    will be assigned a single binding, binding 0.
*   `s.B` is the second. It will be assigned binding 1.
*   `s.C` is the third. It will be assigned the next available binding, which is
    binding 3.

This behavior is different from DXC. When targeting SPIR-V, DXC tries to assign
all of the resources in the struct with continuous bindings where each resource
gets one binding for each element. In this example, the binding assignments in
DXC are as follows:

-   `D` is assigned binding 2.
-   `A` is assigned binding 3.
-   `B` is assigned binding 7.
-   `C` is assigned binding 9.

### Dynamic indexing of resource arrays in a struct

Consider the following HLSL compute shader where a resource array inside a
struct is dynamically indexed:

```hlsl
RWBuffer<float> A[10];

struct S {
  RWBuffer<float> B[10];
} s;

[numthreads(4,1,1)]
void main() {
  for (int i = 0; i < 5; i++) {
    A[i][0] = 1.0;
    s.B[i][0] = 1.0;
  }
}
```

When targeting DXIL, DXC reports an error for this code: `error: Index for
resource array inside cbuffer must be a literal expression`. This is a
fundamental limitation of the DXIL representation for resources in structs. This
limitation does not exist when targeting SPIR-V.

This case will still work in Clang.

*   `A` will be assigned binding 0.
*   `s.B` will be assigned binding 1.

Note that in DXC `s.B` is assigned binding 10.

### Dynamic resource indexing

Consider the following HLSL compute shader where a resource array is dynamically
indexed: 

```hlsl
RWBuffer<float4> A[8]; RWBuffer<float4> B;

RWBuffer<float4> GetBuffer(uint index) { return A[index]; }

[numthreads(8, 3, 4)] void main(uint3 dispatchThreadId : SV_DispatchThreadID) {
RWBuffer<float4> input = GetBuffer(dispatchThreadId.x);

float4 value = float4(0, 0, 0, 0);

switch (dispatchThreadId.y)
{
    case 0:
        switch (dispatchThreadId.z)
        {
            case 0: value = input[0]; break;
            case 1: value = input[1]; break;
            case 2: value = input[2]; break;
            case 3: value = input[3]; break;
        }
        break;
    case 1:
        switch (dispatchThreadId.z)
        {
            case 0: value = input[4]; break;
            case 1: value = input[5]; break;
            case 2: value = input[6]; break;
            case 3: value = input[7]; break;
        }
        break;
    case 2:
        switch (dispatchThreadId.z)
        {
            case 0: value = input[8]; break;
            case 1: value = input[9]; break;
            case 2: value = input[10]; break;
            case 3: value = input[11]; break;
        }
        break;
}

B[dispatchThreadId.x] = value;
}
```

In this example, the `A` array is indexed using `dispatchThreadId.x`, which is
not a compile-time constant. This is an example of dynamic resource indexing.
The selected buffer is then read from based on `dispatchThreadId.y` and
`dispatchThreadId.z`.

This pattern is supported when generating SPIR-V. However, it illustrates the
difficulty of implementing an option like `-fspv-flatten-resource-arrays`. To
flatten the resource array, a pass would be required to replace the array with
individual resources (e.g., `A_0`, `A_1`, etc.). To handle the dynamic index,
the compiler would have to generate code for each possible index, leading to
significant code duplication. The nested `switch` statements further complicate
this, as the entire switch structure would need to be duplicated for each
resource in the array. This is why supporting such an option adds significant
complexity and maintenance overhead.

### Resource in constant buffer

Consider the following HLSL compute shader where resources are declared inside a
`cbuffer`:

```hlsl
cbuffer MyResources
{
    RWBuffer<int> A;
    int idx;
    int value;
};

[numthreads(1, 1, 1)]
void main()
{
    A[idx] = value;
}
```

In this example, `A` is declared in the `MyResources` constant buffer. When
using implicit bindings, DXC has a specific behavior where the bindings for the
resources inside the cbuffer are assigned before the cbuffer itself. In this
case, `A` will be assigned binding 0, and `MyResources` will be assigned binding
1.

TODO: The exact binding assignment behavior in Clang for this scenario is one of
the open questions to be resolved by this proposal.

### Unused RWStructuredBuffer with Counter

This example shows how bindings are assigned to counter buffers associated with
`RWStructuredBuffer`s when the main resource is unused.

```hlsl
RWStructuredBuffer<float4> rw_buf1 : register(u0);
[[vk::counter_binding(3)]] RWStructuredBuffer<int> rw_buf2 : register(u1);

[numthreads(1, 1, 1)]
void main()
{
    rw_buf1.IncrementCounter();
    rw_buf2.IncrementCounter();
}
```

The binding assignments are as follows:

*   `rw_buf1` and `rw_buf2` are considered unused because `IncrementCounter` is
    the only operation performed on them. As a result, they are optimized away
    and do not receive bindings.
*   The counter for `rw_buf2` is explicitly assigned binding 3 via the
    `vk::counter_binding(3)` attribute.
*   The counter for `rw_buf1` has an implicit binding. It is assigned the first
    available binding in the default descriptor set, which is 0.

### Used RWStructuredBuffer with Counter

Here is the same example, but with the main resources being used.

```hlsl
RWStructuredBuffer<float4> rw_buf1 : register(u0);
[[vk::counter_binding(3)]] RWStructuredBuffer<int> rw_buf2 : register(u1);

[numthreads(1, 1, 1)]
void main()
{
    rw_buf1.IncrementCounter();
    rw_buf2.IncrementCounter();
    rw_buf1[0] = rw_buf2[0];
}
```

The binding assignments are as follows:

*   `rw_buf1` is explicitly bound to `register(u0)`, so it is assigned binding 0
    in the default descriptor set (set 0).
*   `rw_buf2` is explicitly bound to `register(u1)`, so it is assigned binding 1
    in the default descriptor set (set 0). Its counter buffer is explicitly
    assigned binding 3 via the `vk::counter_binding(3)` attribute.
*   The counter for `rw_buf1` has an implicit binding. It is assigned the first
    available binding in the default descriptor set, which is 2 (since 0, 1, and
    3 are already used).

### Implicitly Bound RWStructuredBuffer with Counter

Here is an example where the resources and counters are all implicitly bound.

```hlsl
RWStructuredBuffer<float4> rw_buf1;
RWStructuredBuffer<int> rw_buf2;

[numthreads(1, 1, 1)]
void main()
{
    rw_buf1.IncrementCounter();
    rw_buf2.IncrementCounter();
    rw_buf1[0] = rw_buf2[0];
}
```

The binding assignments are as follows:

*   `rw_buf1` is the first resource declared, so it is assigned binding 0. Its
    associated counter is treated as if declared immediately after, so it is
    assigned binding 1.
*   `rw_buf2` is the next resource, so it is assigned the next available
    binding, which is 2. Its counter is then assigned binding 3.

This behavior differs from DXC, which assigns bindings to all main resources
first, followed by the counter resources. In DXC, `rw_buf1` would get binding 0,
`rw_buf2` would get binding 1, the counter for `rw_buf1` would get binding 2,
and the counter for `rw_buf2` would get binding 3.

### RWStructuredBuffer in a Non-Default Descriptor Set

This example shows a resource in a non-default descriptor set.

```hlsl
RWStructuredBuffer<float4> rw_buf1 : register(u0, space1);

[numthreads(1, 1, 1)]
void main()
{
    rw_buf1.IncrementCounter();
    rw_buf1[0] = 0;
}
```

The binding assignments are as follows:

*   `rw_buf1` is explicitly assigned to `register(u0, space1)`, so it receives
    binding 0 in descriptor set 1.
*   The counter for `rw_buf1` has an implicit binding and is placed in the same
    descriptor set as the main resource. It is assigned the first available
    binding in set 1, which is 1.

### Append/Consume Buffers with Counters

This example demonstrates `AppendStructuredBuffer` and
`ConsumeStructuredBuffer`, which have implicit counters and implicit bindings.

```hlsl
AppendStructuredBuffer<float4> append_buf;
ConsumeStructuredBuffer<float4> consume_buf;

[numthreads(1, 1, 1)]
void main()
{
    float4 val = consume_buf.Consume();
    append_buf.Append(val);
}
```

The binding assignments are as follows:

*   `append_buf` is the first resource declared, so it is assigned binding 0.
    Its associated counter is assigned binding 1.
*   `consume_buf` is the next resource, so it is assigned binding 2. Its counter
    is assigned binding 3.

This behavior is consistent with DXC. It is important to note that DXC's
handling of counter buffers for `AppendStructuredBuffer` and
`ConsumeStructuredBuffer` is different from its handling of `RWStructuredBuffer`
counters. For `RWStructuredBuffer`, DXC assigns counter bindings after all main
resources have been assigned bindings. This proposal adopts the
`AppendStructuredBuffer` behavior for all counter resources to ensure
consistency.

### Unbounded arrays

```hlsl
RWBuffer<int> A[];
RWBuffer<int> B[];

[numthreads(1, 1, 1)]
void main()
{
    A[0][0] = B[0][0];
}
```

In HLSL, `A[]` and `B[]` are declared as unbounded (or runtime-sized) arrays of
resources. In Vulkan, this concept maps to a descriptor binding that is an array
of descriptors. Each declaration (`A` and `B`) will be assigned a single,
separate descriptor binding. For example, with implicit bindings:

*   `A` will be assigned to binding 0 in the default descriptor set.
*   `B` will be assigned to binding 1 in the default descriptor set.

This behavior differs significantly from the model for DXIL, as detailed in
[0024-implicit-resource-binding.md](0024-implicit-resource-binding.md). In DXIL,
an unbounded array consumes all remaining binding slots in its register space.
Consequently, DXIL is limited to a single unbounded resource array per register
space. The SPIR-V approach is more flexible, allowing multiple unbounded arrays
to be used by assigning each to its own descriptor binding.

### Constexpr expressions in attributes

This example shows how `constexpr` expressions can be used as arguments to the
`vk::binding` attribute.

```hlsl
constexpr int get_binding(int i) {
    return i + 1;
}

static const int kMySet = 1;

[[vk::binding(get_binding(1) + 1, kMySet)]] RWBuffer<float4> A;

[numthreads(1, 1, 1)]
void main(uint3 dispatchThreadId : SV_DispatchThreadID)
{
    A[0] = 1.0f;
}
```

The compiler will evaluate the `constexpr` expressions at compile time and use
the resulting values for the binding and set assignments.

*   `A` is assigned binding 3 in descriptor set 1.

## Open questions

### Should unused resources be assigned a binding?

**DECISION: Assigning implicit bindings will be done after optimizations. No one
expressed that they rely on unused resources reserving a binding. This behavior
matches DXIL in DXC, so we don't expect many users to rely on the SPIR-V
behavior in DXC.**

When targeting SPIR-V in DXC, resources are assigned bindings before
optimization passes run. This leads to unused resources receiving a binding. If
we assign implicit bindings in the backend, this will occur after optimizations,
which can affect the final binding assignments for other resources. If we want
to maintain compatibility with DXC's behavior, we must decide how to handle
these unused resources.

Assigning binding after optimization is consistent with the behavior when
targeting DXIL in both DXC and Clang. This will help us align better with their
implementation.

Possible solutions:

1.  Move the implicit binding assignment pass out of the backend to run before
    optimizations.
2.  Add an attribute to both binding intrinsics to prevent optimizers from
    removing them. Unused resources could then be removed in a later pass after
    implicit bindings have been assigned.
3.  Add a target intrinsic to be a fake use of the resource handle to keep it
    alive until it is no longer needed.

### Do we still need `-fvk-auto-shift-bindings`?

**DECISION: This option does not seem to be used. It also has complications in
implementing it, so we will not implement it in Clang.**

This option changes a resource's binding based on the `-fvk-*-shift` options.
Supporting this would require the backend pass to access the values of the shift
options and know the register type (`b`, `s`, `t`, `u`) for each resource.

### Do we still need `-fspv-flatten-resource-arrays`?

**DECISION: This option does not seem to be used. It also has complications in
implementing it, so we will not implement it in Clang.**

Supporting this option would require assigning multiple bindings to a single
resource array. This would likely necessitate an extra pass to replace the
resource array with individual resources. This pass is non-trivial to implement,
especially with dynamic indexing, as it requires code duplication and
specialization. This would add significant maintenance overhead to LLVM and
should only be implemented if it addresses a critical need for users who lack a
simpler workaround at the HLSL source level.

### Do we still need the `-fvk-*-shift` options?

Supporting these options means that when assigning a binding, Clang must add an
offset based on the register type:

*   If the declaration has `register(bB, spaceS)`, the offset is from
    `-fvk-b-shift`.
*   If the declaration has `register(sB, spaceS)`, the offset is from
    `-fvk-s-shift`.
*   If the declaration has `register(tB, spaceS)`, the offset is from
    `-fvk-t-shift`.
*   If the declaration has `register(uB, spaceS)`, the offset is from
    `-fvk-u-shift`.

While not difficult to implement, this adds to long-term maintenance costs.

### Do we still need the `-fspv-preserve-bindings` option?

This option tells the compiler to not remove unused bindings. The option is
useful if the developer wants to have the same resource assignement to all
shaders regardless of which resources are used, and know the binding and set of
every resource by doing reflection on just a single shader.

As with assigning bindings to unused resources, this could be implemented by
adding a fake use of the resource handle that survives until instruction
selection. The variable is created during instruction selection. However, we
will have to make sure that we do not remove the unused variables after
instruction selection.

### What is the order ID of resources declared in cbuffers?

When using implicit bindings, DXC ensures that the binding number for a resource
within a `cbuffer` is smaller than the binding number of the `cbuffer` itself.
The equivalent behavior in Clang is currently undefined and needs to be
specified.

## Alternatives considered (Optional)

## Acknowledgments (Optional)
