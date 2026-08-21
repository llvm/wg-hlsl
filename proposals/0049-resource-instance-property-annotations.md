---
title: "[0049] - Resource Instance Property Annotations"
params:
  status: Accepted
  authors:
    - inbelic: Finn Plummer
  sponsors:
    - inbelic: Finn Plummer
---

* Related proposals: [0006], [0015], [0018], [0022], [0023]

## Introduction

This proposal resolves how the non-structural resource instance properties
`HasCounter`, `IsGloballyCoherent`, and `IsReorderCoherent` will be
represented. `HasCounter` is observable from the counter operations already
present in IR and so it does not require any additional representation. Global
and reorder coherence express source-level semantics that are not observable
from the resource operations and so they will be preserved with an explicit
resource coherence annotation. The per-target lowering of each property is
described in the sections below.

## Has Counter

Use of a resource counter is able to be retained in IR. Every increment or
decrement is represented by an `llvm.dx.resource.updatecounter` operation whose
handle operand identifies the resource instances that require a counter, and
whose increment operand records the direction of the update.

When lowering to DirectX, resource analysis will visit these operations before
they are lowered to `dx.op.bufferUpdateCounter` and trace each handle to the
resource instances that require a counter. This is the `CounterDirection`
property that [0022] resolves on `ResourceInfo`.

`HasCounter` remains the name of the derived DXIL resource metadata field and
of the corresponding `dx.op.annotateHandle` property bit. Final DXIL lowering
will use the analysis result to set both, with `HasCounter` being true for any
instance with a consistent counter direction.

When lowering to SPIR-V, the resource counter is treated as its own variable
and the counter updates map to the corresponding SPIR-V operations. These are
lowered in the standard fashion.

An explicit annotation is therefore not required.

## Global Coherence

The `globallycoherent` qualifier requires synchronization of a UAV to make its
writes visible across thread groups rather than only within the current thread
group. This is a source-level semantic on a resource instance and is not
retained through the use of operations on that resource. For example, the
following produce the same resource type, handle creation, and access
operations:

```hlsl
RWStructuredBuffer<uint> Buffer;
```

```hlsl
globallycoherent RWStructuredBuffer<uint> Buffer;
```

During codegen we would be able to modify how the resource is accessed by
emitting `load`/`store` methods with memory semantics or by introducing
barriers. However, LLVM `load`s and `store`s do not have memory semantics
available to distinguish the cache properties of the access, similar for atomic
access. Memory barriers can only apply to a memory space and not to specific
resources. So we are unable to create an analysis pass to infer the property.

## Reorder Coherence

Briefly, the `reordercoherent` qualifier, used with a
`Barrier(UAV_MEMORY, REORDER_SCOPE)`, makes UAV writes performed before a
reorder point visible to subsequent non-atomic reads for the same dispatch
index, and is used within Shader Execution Reordering (SER).

Work to support SER is out of scope of this proposal, but we should consider
that, as with global coherence, the qualifier does not change the resource
access operations and so following the same reasoning, reorder coherence must
also be explicitly annotated.

## Explicit Coherence Annotation

Global and reorder coherence are required to be explicitly annotated during
code generation when the corresponding HLSL attribute is present. New
`llvm.[dx|spv].resource.annotatecoherence` intrinsics will be defined to take a
resource handle and a coherence enum kind and return a handle to the resource
instance.

_Note_: `globallycoherent` provides the stronger guarantee and therefore implies
`reordercoherent` so these are mutually exclusive kinds. This will be diagnosed
during semantic analysis of the attributes.

### Intrinsic Definition

The intrinsics are overloaded on the handle type and return the same type as
their handle operand. For DirectX this is:

```llvm
declare target("dx.RawBuffer", i32, 1, 0)
  @llvm.dx.resource.annotatecoherence.tdx.RawBuffer_i32_1_0t(
      target("dx.RawBuffer", i32, 1, 0) %handle, i32 immarg %kind)
```

and equivalently for `llvm.spv.resource.annotatecoherence` over the SPIR-V
handle types described in [0018].

The `%kind` operand is an `immarg` so that the coherence state is always
statically known to resource analysis. It is one of:

| Value | Kind               | Source qualifier   |
|-------|--------------------|--------------------|
| 0     | `GloballyCoherent` | `globallycoherent` |
| 1     | `ReorderCoherent`  | `reordercoherent`  |

The absence of this intrinsic denotes no coherence guarantees.

For example, the following declaration:

```hlsl
globallycoherent RWStructuredBuffer<uint> Buf : register(u0);
```

produces:

```llvm
%h = call target("dx.RawBuffer", i32, 1, 0)
    @llvm.dx.resource.handlefrombinding(i32 0, i32 0, i32 1, i32 0, i1 false)
%ah = call target("dx.RawBuffer", i32, 1, 0)
    @llvm.dx.resource.annotatecoherence(
        target("dx.RawBuffer", i32, 1, 0) %h, i32 0)
```

where `%ah` is used in place of `%h` by all subsequent accesses to `Buf`.

The intrinsics have no target instruction of their own. They are consumed by
resource analysis and erased by the corresponding lowering pass.

### Annotating a Resource Instance

A resource instance may have more than one handle creation, and each is
annotated independently. During analysis a resource instance will be marked
with the corresponding coherence property if any of its uses is annotated, or
vice versa, if it was assigned to a resource instance with a coherence
property. For example, if a global resource does not have any coherence
properties but a local resource is assigned to it, then this is propogated up
to global resource instance. A best-effort warning can be emit during SemaHLSL
to describe these cases early, otherwise, warnings can be generated when the
analysis is consumed.

### Lowering

When lowering to DirectX, resource analysis will consume the annotation and
final lowering will include the selected coherence state in both of the places
that DXIL records it:

- the UAV resource metadata record, where global coherence is a dedicated field
  of the record and reorder coherence is carried in the record's extended tag
  list
- the resource properties passed to `dx.op.annotateHandle`, where each kind has
  its own property bit

This mirrors `HasCounter`, which is likewise emitted in both the resource
metadata and the handle properties.

When lowering a globally coherent resource to SPIR-V, the annotation is consumed
by the same legalization pass that lowers the `spirv.VulkanBuffer` handle
described in [0018]. Global coherence causes the `OpVariable` created for the
resource to be decorated with `Coherent`.

When the Vulkan memory model is in use, the `Coherent` decoration is deprecated.
In which case the equivalent is to mark the accesses instead of the variable,
decorating the pointers `NonPrivatePointer` and giving the loads and stores
through them the `MakePointerVisible` and `MakePointerAvailable` operands with
`QueueFamily` scope. This will require a pass during SPIR-V lowering but all
required info to decorate the accesses is retained in the annotation intrinsics.

Currently, reorder coherence has no SPIR-V mapping, and defining it is out of
scope of this proposal. This will need to be revisited when SER is addressed.

## Alternatives considered

### Give the accesses memory semantics

The most direct representation would be for the loads and stores through a
coherent resource to carry the memory semantics themselves, which would make
the property inferable rather than annotated. As described in the Global
Coherence section, LLVM has does not have such semantics available on `load`
and `store`.

This would be possible but would require additions to LLVM's memory semantics,
which is a substanial change due to it's wide use. Further, it is unclear if
the additional fidelity provides substantial benefit to memory access
optimizations, as this only models cross thread-group accesses.

### Allow barriers to be resource specific

When emitting the resource operations, it would be possible to mark the memory
access using memory barrier instructions. As described in the Global Coherence
section, current LLVM memory barriers apply to a memory space rather than to a
specific resource instances.

This would require us to add a new barrier type that is resource specific and
would follow a similar pattern as the annotation intrinsic above. However, the
intrinsic's placement would hold more fine-grained meaning for optimization or
otherwise.

### Encode coherence in the handle type

Coherence could be another parameter of the resource target extension type, as
`IsWriteable` and `IsROV` already are. This is not desired as, following
[0022], coherence is a property of a resource instance rather than of a resource
type. Further, the types would propagates into the signature of every operation
that takes a handle and into every overload name.

### A generic resource property annotation

Rather than a coherence specific intrinsic, a single annotation taking a
property kind and a value could carry any future resource instance specific
property. This was not desired for now because coherence is the only property
that requires an annotation.

[0006]: 0006-resource-representations.md
[0015]: 0015-resource-attributes-in-dxil-and-spirv.md
[0018]: 0018-spirv-resource-representation.md
[0022]: 0022-resource-instance-analysis.md
[0023]: 0023-typed-buffer-counters.md
