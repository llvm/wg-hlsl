---
title: "[0023] - Representing counter variables for typed buffers"
params:
  status: Design In Progress
  authors:
    - s-perron: Steven Perron
---

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

The counter variables are a core feature in HLSL and must be represented.

## Proposed solution

Access to resources occurs through handles stored in a static global variable.
In SPIR-V, a resource and its counter are represented by distinct handles, while
in DXIL they share the same handle. We propose that the IR representation adopt
the more explicit SPIR-V model, representing the main buffer and its counter
with two separate handles. The DXIL backend will then be responsible for merging
these into a single handle.

We propose that `RWStructuredBuffer` objects, and others with a counter, be
modified to include two separate handles: one for main storage (`bufferHandle`)
and one for the counter (`counterHandle`). The `bufferHandle` is initialized as
usual via a call to `llvm.dx.resource.handlefrom*binding` or
`llvm.spv.resource.handlefrom*binding`, depending on the target.

To establish an explicit link between the resource and its counter, we propose
introducing two new SPIR-V specific intrinsics:

*   `llvm.spv.resource.counterhandlefromimplicitbinding(ResourceHandle,
    order_id, space_id)`
*   `llvm.spv.resource.counterhandlefrombinding(ResourceHandle, binding_id,
    space_id)`

For DirectX, the counter handle is an alias for the main resource handle.
Clang's code generation will handle this by simply copying the main resource
handle.

The `counterHandle` will be initialized by calling one of these intrinsics,
passing the `bufferHandle` of the main storage as the first argument. This makes
the relationship explicit in the IR, which simplifies SPIR-V code generation for
the `CounterBuffer` decoration. For the DXIL backend, this allows it to
recognize that the counter handle is an alias for the main buffer handle and
merge them accordingly. For cases where the counter binding needs to be
explicitly specified, a `[[vk::counter_binding]]` attribute will be available.

## Detailed design

The implementation will introduce a two-handle model directly into the resource
class definition. This will be achieved through a combination of new AST nodes,
Sema actions, and code generation logic.

### AST and Type Representation

1.  **Two-Member Struct:** Resource types that support counters (e.g.,
    `RWStructuredBuffer`) will be defined as structs containing two handle
    members: `__handle` for the primary data and `__counter_handle` for the
    counter.

2.  **`IsCounter` Attribute:** To differentiate the types of the two handles, a
    new attribute, `[[hlsl::is_counter]]`, will be introduced. The type of the
    `__counter_handle` member will be the same as the type for `__handle` except
    it will be annotated with this attribute. This will be tracked in the AST by
    adding an `IsCounter` flag to `HLSLAttributedResourceType::Attributes`. By
    making the counter handle's type identical to the main resource handle's
    type, distinguished only by this attribute, we enable flexible and correct
    code generation. Clang's code generation for each target
    (`clang/lib/CodeGen/Targets/`) will be responsible for interpreting this
    attribute. The implementation for the DirectX target can ignore this
    attribute, resulting in the same target type for both handles, which aligns
    with its single-handle model. Conversely, the implementation for the SPIR-V
    target can detect this attribute and generate a distinct and appropriate
    target type for the counter (e.g., a buffer of `i32`), fitting its
    separate-resource model.

3.  **Sema and Builtin Construction:**

    *   In `HLSLExternalSemaSource.cpp`, the `setupBufferType` function will be
        modified. For UAVs that can have counters, it will call
        `addCounterHandleMember` in the `BuiltinTypeDeclBuilder`.
    *   `addCounterHandleMember` will create the `__counter_handle` field and
        apply the necessary attributes, including `HLSLIsCounterAttr`, to its
        type.

4.  **Counter Operations:** Methods like `IncrementCounter` and
    `DecrementCounter` will be modified in `HLSLBuiltinTypeDeclBuilder.cpp` to
    operate on the `__counter_handle` member instead of the `__handle` member,
    directing the atomic operations to the correct resource.

### Explicit Counter Binding with `[[vk::counter_binding]]`

To allow for explicit control over counter bindings, a new attribute,
`[[vk::counter_binding(binding)]]`, will be introduced. Internally, this will be
a new attribute HLSLVkCounterBindingAttr that will be modeled after the
`HLSLResourceBindingAttr`. It will have a value for an explicit binding or an
implicit order id.

### Initialization and Binding

The core of this design lies in how these two handles are initialized. In Sema,
new static methods will be added to the resource class to initialize them.

1.  **New Static Methods:** Four new static methods will be added to
    counter-enabled resource classes to handle all combinations of implicit and
    explicit bindings for the main resource and its counter:

    *   `__createFromBindingWithImplicitCounter(unsigned registerNo, unsigned
        spaceNo, int range, unsigned index, const char *name, unsigned
        counterOrderId)`:

        Creates a resource with an explicit binding for the main buffer and an
        implicit binding for its counter.

    *   `__createFromImplicitBindingWithImplicitCounter(unsigned orderId,
        unsigned spaceNo, int range, unsigned index, const char *name, unsigned
        counterOrderId)`:

        Creates a resource with implicit bindings for both the main buffer and
        its counter.

    *   `__createFromBindingWithCounter(unsigned registerNo, unsigned spaceNo,
        int range, unsigned index, const char *name, unsigned
        counterRegisterNo)`:

        Creates a resource with an explicit binding for the main buffer and an
        explicit binding for its counter. The counter will be in the same space
        as the main buffer.

    *   `__createFromImplicitBindingWithCounter(unsigned orderId, unsigned
        spaceNo, int range, unsigned index, const char *name, unsigned
        counterRegisterNo)`:

        Creates a resource with an implicit binding for the main buffer and an
        explicit binding for its counter. The counter will be in the same space
        as the main buffer.

2.  **Sema Logic:** In `SemaHLSL.cpp`, the `initGlobalResourceDecl` function
    will check if a resource type has a second field with a handle type that has
    `[[hlsl::is_counter]]` attribute. If it does, it will emit a call to the
    appropriate `...WithCounter` static method instead of the regular creation
    methods.

3.  **Handle Creation:** The `...With*Counter` methods, defined in
    `clang/lib/Sema/HLSLBuiltinTypeDeclBuilder.cpp`, will initialize the two
    handles using a combination of existing and new built-in functions defined
    in `clang/include/clang/Basic/Builtins.td`.

    *   The `__handle` (main data) will be initialized using the existing
        `__builtin_hlsl_resource_handlefrombinding` or
        `__builtin_hlsl_resource_handlefromimplicitbinding` built-ins.
    *   To initialize the `__counter_handle`, new built-in functions will be
        introduced: `__builtin_hlsl_resource_counterhandlefromimplicitbinding`
        and `__builtin_hlsl_resource_counterhandlefrombinding`. These built-ins
        will take the main resource handle (`__handle`) as an argument, along
        with the counter's binding information.
    *   During Clang's code generation, these new built-ins will be lowered to
        their corresponding target-specific LLVM intrinsics for SPIR-V
        (`llvm.spv.resource.counterhandle...`). For DirectX, since the counter
        shares the same handle as the main resource, the built-in will be
        replaced by a simple copy of the main resource handle. This approach
        correctly models the relationship between the main resource and its
        counter directly in the IR, as described in the "Proposed solution".

### Array Handling

For arrays of resources, the counter binding information is stored in the
`HLSLVkCounterBindingAttr` of the array declaration itself. When Sema acts on the
variable declaration, it will add an `HLSLVkCounterBindingAttr` with an implicit
binding if the attribute does not already exist. When an array element is
initialized with a call to a `__createHandle...` function during CodeGen, the
appropriate `...With*Counter` version of the create function will be called for
resources that have the `HLSLVkCounterBindingAttr`.

When the SPIR-V backend encounters a `llvm.spv.resource.counterhandlefrom...`
intrinsic, it will use the main resource handle to access the array size, index,
and name. This information is then used to construct the counter resource. This
approach avoids duplicating information and ensures that the counter resource is
correctly associated with its main resource.

## LLVM IR Generation and Backend Handling

1.  **SPIR-V Target Type Generation:** In `clang/lib/CodeGen/Targets/SPIR.cpp`,
    the `getHLSLType` function will check for the `IsCounter` flag on the
    `HLSLAttributedResourceType`. If the flag is present, it will generate a
    `target("spirv.VulkanBuffer", ...)` in the `StorageBuffer` storage class
    with an `i32` element type, correctly representing the counter as a 32-bit
    integer buffer in SPIR-V.

2.  **SPIR-V Backend Intrinsic Handling:** The SPIR-V backend in LLVM will be
    updated to recognize the `llvm.spv.resource.counterhandlefrom...`
    intrinsics. When it encounters one, it will generate a new, distinct
    `OpVariable` for the counter buffer. It will then use the information from
    the intrinsic (linking the main handle to the counter handle) to emit an
    `OpDecorate` instruction with the `CounterBuffer` decoration, pointing from
    the main buffer's `OpVariable` to the newly created counter buffer's
    `OpVariable` when necessary. The backend will use the main resource handle
    to access the array size, index, and name for the counter resource. The name
    of the counter variable will be generated by appending "_counter" to the
    name of the main resource.

## Alternatives considered

### Independent `llvm.spv.resource.handlefrombinding` calls

The initial proposal was to initialize both the main buffer handle and the
counter handle with separate calls to `llvm.spv.resource.handlefrombinding` (or
the `spv` equivalent). This would have treated them as two entirely independent
resources from the point of view of the frontend.

However, this approach is problematic for both DXIL and SPIR-V: 1. **Impossible
to Unify Calls for DXIL:** The original idea suggested the two
`llvm.spv.resource.handlefrombinding` calls could be identical. This is not
feasible. A resource like `RWStructuredBuffer<T> MyBuffer : register(u0)` has an
explicit binding and the name "MyBuffer". Its counter, however, has an implicit
binding assigned by the compiler and a different name (e.g.,
"MyBuffer_counter"). Because the binding points and names are different, the
arguments to their respective `llvm.spv.resource.handlefrombinding` calls must
also be different, making them impossible to common. 2. **Lost Connection:**
Treating the counter as a completely separate resource severs the explicit link
between the main buffer and its counter in the IR. For DXIL, this makes it
difficult to know that the two resources are related and share the same
underlying handle. For SPIR-V, this link is required to emit the `CounterBuffer`
decoration on the main buffer, pointing to the counter. Reconstructing this
relationship in the backend would be complex and rely on fragile naming
conventions.

### Multiple binding numbers on `llvm.spv.resource.handlefrombinding`

One possible solution is to incorporate multiple binding locations into
`llvm.spv.resource.handlefrombinding`. This would allow the SPIR-V backend to
expand the call into multiple resources. However, this solution is not ideal
because it would necessitate the creation of an ad hoc target type within the
SPIR-V backend.

In contrast, the proposed solution only requires a single target type to
represent a generic Vulkan buffer. This type could potentially be reused by any
language targeting Vulkan.

### Including the binding for the counter in the handle type.

The inclusion of the counter's binding number in the type returned by
`llvm.spv.resource.handlefrombinding` was another potential solution. However,
this solution is not feasible due to resource aliases. As an example, it would
be impossible to determine the type for a RWStructuredBuffer function parameter
because it lacks a single binding location.
