---
title: "[NNNN] - Dynamic resources"
params:
  authors:
    - hekota: Helena Kotas
  status: Under Consideration
  sponsors:
    - hekota: Helena Kotas
---


## Introduction

Shader Model 6.6 introduced dynamic resources, also known as _bindless
resources_ or _directly indexed resources_. This feature allows shaders to
create resources from descriptors by directly indexing the CBV/SRV/UAV heap or
the sampler heap. The CBV/SRV/UAV heap is also called the resource descriptor
heap.

HLSL exposes these heaps through two built-in global objects:
`ResourceDescriptorHeap` and `SamplerDescriptorHeap`. Indexing either object
produces an intermediate value that can be converted to a resource or sampler
object. Resources created this way do not require binding locations or root
signature descriptor-table mappings.

## Motivation

Dynamic resources are part of the HLSL language and we need to support it in
Clang.

## Current Behavior in DXC

This section documents how DXC handles dynamic resources.

### Example 1 - Assigning to local resource variable

Resource instance aquired by direct indexing is usually assigned to a local
resource variable:

```cpp
cbuffer CB {
    uint Index;
}

[numthreads(4, 1, 1)]
void main() {
  RWBuffer<int> Buf = ResourceDescriptorHeap[Index];
  Buf[0] = 123;
}
```
https://godbolt.org/z/sYfbe9GEs

The same local variable can be used for different resource instances:

```cpp
cbuffer CB {
    uint Index;
}

[numthreads(4, 1, 1)]
void main() {
  RWBuffer<int> Buf;
  Buf = ResourceDescriptorHeap[Index];
  Buf[0] = 123;

  Buf = ResourceDescriptorHeap[Index + 1];
  Buf[0] = 456;
}
```
https://godbolt.org/z/xE3P9Yzff

### Example 2 - Function argument

Directly indexed resource instance can also be used as a function
argument(without first assigning it to a local variable).

```
cbuffer CB {
    uint Index;
}

void foo(RWBuffer<int> Buf) {
  Buf[0] = 123;
}

[numthreads(4, 1, 1)]
void main() {
  foo(ResourceDescriptorHeap[Index]);
}
```
https://godbolt.org/z/EjaK4rxhe

### Example 3 - Using directly indexed heap as a resource class

The result of the direct indexing into `ResourceDescriptorHeap` or
`SamplerDescriptorHeap` cannot be directly used as if it was a resource class:

```cpp
cbuffer CB {
    uint Index;
}

[numthreads(4, 1, 1)]
void main() {
  int i = ResourceDescriptorHeap[Index].Load(10);
}
```
https://godbolt.org/z/6qP6eeYsj

### Example 4 - Indexing into a wrong heap does not get diagnosed

Indexing into a `SamplerDescriptorHeap` to get a CVB/SRV/UAV resource, or
indexing into a `ResourceDescriptorHeap` to get a SamplerState resource does not
produce an error. This is something the Clang implementation could possibly
improve upon.

```cpp
cbuffer CB {
    uint Index;
}

[numthreads(4, 1, 1)]
void main() {
  RWBuffer<int> Buf = SamplerDescriptorHeap[Index];
  int i = Buf[0];
}
```
https://godbolt.org/z/fnMhbeeEr

### Example 5 - Assigning to a Global Variable

The result of heap indexing cannot be used to initialize a global resource
variable because DXC ignores initializers on external globals:

```cpp
RWBuffer<int> GlobalBuf = ResourceDescriptorHeap[5];

[numthreads(4, 1, 1)]
void main() {
  GlobalBuf[0] = 123;
}
```
https://godbolt.org/z/Td7vMz1vf

DXC produces the following diagnostics:

```text
warning: Initializer of external global will be ignored
error: Explicit load/store type does not match pointee type of pointer operand
```

## Proposed solution

At the point of indexing into `ResourceDescriptorHeap` or
`SamplerDescriptorHeap`, the compiler does not yet know the resource type with
which the descriptor will be used. That type becomes known only when the result
is assigned to or used to initialize a resource object, or passed as a function
argument.

Therefore, indexing a heap global will not produce a resource handle directly.
Instead, it will return a small internal struct, `__hlsl_heap_resource_info`,
that carries the heap index and a flag identifying the indexed heap.

Every resource class will have an implicit constructor that accepts
`__hlsl_heap_resource_info` and it will use use this information and a Clang
built-in function(s) to create a concrete handle type from heap. Standard C++
implicit conversion rules then make the assignment, initialization, and
function-argument cases work without special handling in `Sema`. This design
also supports creating multiple handles for resources with counters.

## Detailed design

### Frontend (Clang AST/Sema)

#### Heap Resource Info Struct

The internal struct `__hlsl_heap_resource_info` will be defined in
`HLSLExternalSemaSource` before any resource classes so it can then be used as
an argument of the heap resource constructor. The struct will look like this:

```cpp
struct __hlsl_heap_resource_info {
  unsigned int Index;
  bool isSamplerHeap;
};
```

#### Heap Globals

The global heap variables `ResourceDescriptorHeap` and `SamplerDescriptorHeap`
can be in a new builtin header `hlsl/hlsl_resources.h`, which will be included
from the default header `hlsl.h`.

The definition would look like this:

```cpp
namespace hlsl {

#define _HLSL_AVAILABILITY(platform, version)                                  \
  __attribute__((availability(platform, introduced = version)))

template <bool IsSamplerHeap>
struct _HLSL_AVAILABILITY(shadermodel, 6.6) DescriptorHeapStruct {
  __hlsl_heap_resource_info operator[](uint32_t Index) {
    return __hlsl_heap_resource_info{Index, IsSamplerHeap};
  }
};

_HLSL_AVAILABILITY(shadermodel, 6.6)
static DescriptorHeapStruct<false> ResourceDescriptorHeap;

_HLSL_AVAILABILITY(shadermodel, 6.6)
static DescriptorHeapStruct<true> SamplerDescriptorHeap;

} // namespace hlsl
```

#### Heap Constructors on Resource Types

Add resource types will get a new constructor that takes
`__hlsl_heap_resource_info` and that will call a new Clang builtin function
`__builtin_hlsl_resource_handlefromheap`, passing in the heap index and whether
the indexed heap is a Sampler heap or not.

For example:

```c++
template <typename T> struct RWBuffer {
  ...
public:
  RWBuffer(__hlsl_heap_resource_info HeapResInfo) {
    __handle = __builtin_hlsl_resource_handlefromheap(__handle, HeapResInfo.Index,     HeapResInfo.IsSamplerHeap);
  };
};
```

The first argument of the builtin function will be used to infer the return
handle type.

For resource types with counters the constructor will use additional builtin
`__builtin_hlsl_resource_counterhandlefromheap` to initialize the counter
handle.

Because this constructor is implicit and takes exactly one argument, all of the
DXC usage patterns in the previous section will fall out of ordinary overload
resolution.

### CodeGen (Clang)

Clang CodeGen will lower `__builtin_hlsl_resource_handlefromheap` to the
target-specific intrinsic `llvm.[dx|spv].resource.handlefromheap(i32 Index, i1
IsSamplerHeap)`, overloaded on the resource's target extension handle type.

For SPIR-V targets, CodeGen will lower
`__builtin_hlsl_resource_counterhandlefromheap` to
`llvm.spv.resource.counterhandlefromheap`. DirectX does not represent the
counter as a separate descriptor, so CodeGen will instead return the main
resource handle unchanged. This matches the existing handling of counter handles
created from implicit and explicit bindings.

### Backend (LLVM)

The DirectX and SPIR-V backends will gain the new intrinsic
`llvm.[dx|spv].resource.handlefromheap`. SPIR-V will also support
`llvm.spv.resource.counterhandlefromheap`. The `handlefromheap` intrinsic takes
a heap index and a flag that selects either the sampler heap or the CBV/SRV/UAV
heap, and returns a value of the concrete resource target type.

Passes that currently identify resource-handle creation by looking for
`llvm.[dx|spv].resource.handlefrombinding` must also recognize the corresponding
`handlefromheap` intrinsic.

Resources created from a descriptor heap do not have bindings. Existing passes
assume that every resource has a binding and use it to distinguish resource
instances of the same type. These passes must be updated to support binding-less
resources and to distinguish resource instances created from different heap
index values.

The following LLVM passes will need to be updated:

#### `DXILResourceAnalysis`

The analysis will handle each call to `llvm.dx.resource.handlefromheap` by
creating a binding-less `ResourceInfo`. The `Binding` member of `ResourceInfo`
will become optional, and a new `HeapIndexID` field will distinguish heap
resource instances.

The heap-index operand of `llvm.dx.resource.handlefromheap` is a `Value *`.
`DXILResourceAnalysis` will assign a unique `HeapIndexID` to each distinct
heap-index value.

Heap resources do not participate in binding ID assignment, so `setBindingID`
will be called only for resources that have a binding. To reflect this meaning,
`RecordID` should be renamed to `BindingID`.

#### `DXILRemoveUnusedResources`

The pass should also remove unused resources created by
`llvm.dx.resource.handlefromheap`.

#### `DXILPostOptimizationValidation`

This pass could verify that each directly indexed resource uses the appropriate
descriptor heap. For sampler resources, `llvm.dx.resource.handlefromheap` must
have `IsSamplerHeap` set to `true`. For all other resource classes, it must be
set to `false` to select the CBV/SRV/UAV heap.

#### `DXILTranslateMetadata` and `DXILPrettyPrinter`

`DXILTranslateMetadata` will neither create symbols for heap resources nor emit
entries for them in the `SRV`, `UAV`, `CBuffer`, or `Sampler` metadata lists.

`DXILPrettyPrinter` will omit heap resources from the resource bindings table
printed as a comment in the LLVM assembly.

#### `DXContainerGlobals`

The pass will skip resources without bindings when emitting PSV resource
entries.

#### SPIR-V passes

Preliminary analysis found no SPIR-V-specific passes that recognize
`llvm.spv.resource.handlefrombinding` and therefore need to be extended to
recognize `llvm.spv.resource.handlefromheap`.

### DXIL Lowering

For DirectX targets, `llvm.dx.resource.handlefromheap` will lower to a
`dx.op.createHandleFromHeap` operation followed by `dx.op.annotateHandle`. This
matches the structure of the existing `createHandleFromBinding` lowering.

`dx.op.createHandleFromHeap` takes three operands: the heap index, a flag that
selects the sampler heap, and a flag that indicates whether the index is
non-uniform. The lowering will compute the non-uniform flag using the existing
`hasNonUniformIndex` helper.

For example, the intrinsic call

```llvm
%typed = call target("dx.TypedBuffer", <4 x float>, 1, 0, 0)
    @llvm.dx.resource.handlefromheap.tdx.TypedBuffer_v4f32_1_0_0(i32 3, i1 false)
```

will lower to

```llvm
%0 = call %dx.types.Handle @dx.op.createHandleFromHeap(i32 218, i32 3, i1 false, i1 false)
%1 = call %dx.types.Handle @dx.op.annotateHandle(i32 216, %dx.types.Handle %0,
         %dx.types.ResourceProperties { i32 4106, i32 1033 })
```

### SPIR-V Lowering

TBD

### Shader Flags

Descriptor-heap usage must be recorded in the shader feature flags. The
`DXILShaderFlags` pass will inspect each `llvm.dx.resource.handlefromheap` call
and set `SamplerDescriptorHeapIndexing` when `IsSamplerHeap` is `true`, or
`ResourceDescriptorHeapIndexing` when it is `false`.

### Testing

TBD - Clang tests for AST shape, CodeGen output, and availability diagnostics
  still need to be added.

## Alternatives considered

* **Return `__hlsl_resource_t` directly from the indexing operator.** This is
  not possible because `__hlsl_resource_t` is parameterized by the resource
  class, contained type, and other type attributes that are unknown at the point
  of heap indexing. The concrete handle type becomes known only when the indexed
  value is converted to a specific resource type. `__hlsl_heap_resource_info`
  defers handle creation until that conversion.

## Open questions

* **Diagnosing indexing into the wrong heap.** DXC silently accepts
  `RWBuffer<int> Buf = SamplerDescriptorHeap[Index];` (Example 4). Although the
  heap kind is a compile-time constant in the proposed design, wrapping it in
  `__hlsl_heap_resource_info` makes diagnosing the mismatch during overload
  resolution or construction less straightforward. Should
  `DXILPostOptimizationValidation` diagnose a mismatch between the selected heap
  and the resulting resource class, despite the resulting incompatibility with
  DXC?

## Acknowledgments
