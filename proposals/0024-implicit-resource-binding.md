* Proposal: [0024](0024-implicit-resource-binding.md)
* Author(s): [Helena Kotas](https://github.com/hekota)
* Status: **Design In Progress**

## Introduction

HLSL Resources are runtime-bound data that are provided as input, output, or
both to shader programs. Resources need to be bound to the graphics or compute
pipeline for shaders to access them. In DirectX this is done via descriptors,
which are sometimes referred to as views, handles or registers.

Binding of resources to descriptors in HLSL is done via `register` annotation on
the resource variable declaration, such as:

```c++
RWBuffer<float4> Data : register(u2); 
```

DirectX has four types of descriptors/handles:
- `UAV` - unordered access view (read-write) - using `u` registers
- `SRV` - shader resource view (read-only) - using `t` registers
- `CBV` - constant buffer view (read-only) - using `b` registers
- `Sampler` - sampler (read-only) - using `s` registers

The `register` annotation specifies the first descriptor the resource is bound
to. For simple resources that is the only descriptor the resource needs. In case
of arrays the `register` specifies the start of the description range needed for
the resource array. The dimensions of the array determine the size of the
description range.

The annotation can also include virtual register space:

```c++
Texture2D<float4> Tx : register(t3, space1); 
```

_Note: See the HLSL Language specification section Resource Binding for more
details._

Specifying resource binding on a resource is not mandatory. If a binding is not
provided by the user, it is up to the compiler to assign a descriptor to such
resources. This is called _implicit resource binding_ and it is the focus of
this document.

## Current behavior in DXC

This section documents the implicit resource binding assignment in DXC. For
simplicity the examples below use just the `u` registers and `RWBuffer<float>`
resource, but same binding assignment rules apply to other register and resource
types as well.

### Simple Resource Declarations

Resources without binding assignment that are declared directly at the global
scope are processed in the order they appear in the source code. They are
assigned the first available register slot in `space0`. Unused resources are
optimized away and do not participate in the implicit binding assignment.

#### Example 1.1
```c++
RWBuffer<float> A : register(u0);
RWBuffer<float> B;                 // gets u1
RWBuffer<float> C: register(u2);   // unused
RWBuffer<float> D;                 // gets u2

[numthreads(4,1,1)]
void main() {
  A[0] = D[0] + B[0];
}
```
https://godbolt.org/z/sMs3c8j7T

If `C` is used then `D` gets assigned descriptor `u3`. 

However, if the resources are declared inside a `struct`, their binding seems be
assigned in the order they are referenced (used) in the source code, and not the
order in which they were declared. It is even possible it depends on the order
in which the IR code is generated when a resource is accessed.

#### Example 1.2
```c++
RWBuffer<float> A : register(u0);
RWBuffer<float> C: register(u2);   // unused

struct S {
  RWBuffer<float> B;                 // gets u2
  RWBuffer<float> D;                 // gets u1
} s;

[numthreads(4,1,1)]
void main() {
  A[0] = s.D[0] + s.B[0];
}
```
https://godbolt.org/z/6a1b7Kvz3

The maximum value of the register slot and virtual space number is `UINT_MAX`
(max. value of 32-bit unsigned integer).

### Constant-size Resource Arrays

Constant-size resource arrays declared directly at the global scope are also
processed in the order they appear in the source code. They are assigned the
first range of available decriptors in `space0` that fits the array size
regardless of whether the individual resources in the array are used or not, as
long as at least one of the them is accessed.

If a resource isn't used, the whole resource declaration is optimized away and
its descriptor range is available for use by other resources.

#### Example 2.1
```c++
RWBuffer<float> A : register(u2);
RWBuffer<float> B[4];    // gets u3 because it does not fit before A (range 4)
RWBuffer<float> C[2];    // gets u0 because it fits before A (range 2)
RWBuffer<float> D[50] : register(u6); // unused
RWBuffer<float> E[2];    // gets u7 which is right after B (range 2)

[numthreads(4,1,1)]
void main() {
  A[0] = E[2][0] + C[1][0] + B[1][0];
}
```
https://godbolt.org/z/qha84sjvT

However, if the resource array is defined in a `struct`, the binding seems to be
assigned to the individual array elements in the order they are referenced
(used) in the source code, and possibly in the order the IR code to access the
resource is generated. Additionally, the array elements are treated as
unrelated individual resources:

#### Example 2.2
```c++
struct S {
    RWBuffer<float> B[4]; // s.B.2 gets u3
    RWBuffer<float> C[2]; // s.C.1 gets u1
    RWBuffer<float> E[3]; // s.E.2 gets u0
};                        // s.E.1 gets u4

RWBuffer<float> A : register(u2);
S s;

[numthreads(4,1,1)]
void main() {
  A[0] = s.E[2][0] + s.C[1][0] + s.B[3][0] + s.E[1][0];
}
```
https://godbolt.org/z/Kano8WeYs

This seems wrong. Resource arrays should be bound to a continuous descriptor
range and the range should be reflected in the `createHandleFromBinding`
arguments. It also makes the binding susceptible to change whenever the code
changes and is not something that can be relied upon. 

Another interesting case is when a resource array inside a struct has explicit
binding but not all of the array elements are used. DXC seems to pre-assign the
register slots to the array elements, but does not actually reserve them, which
seems like a bug. So when a particular array element is not used, its register
slot can be (implicitly or explicitly) assigned to another resource.

#### Example 2.3
```c++
RWBuffer<float> A : register(u0);

struct S {
  RWBuffer<float> D[3];
};
S s1[2] : register(u0); // s1.0.D.1 gets u1
S s2[2] : register(u1); // s2.0.D.1 gets u5
RWBuffer<float> B; // gets u2

[numthreads(1,1,1)]
void main() {
  A[0] = s1[0].D[1][0] + s2[1].D[1][0] + B[0];
}
```
https://godbolt.org/z/5rf47heTe

This example shows that if we reserve a continuous descriptor range for resource
array in structs we might break existing code that uses explicit binding and
relies on the current behavior.

Array resources inside structs are also not allowed to use dynamic indexing. In
the following example DXC reports error when the resource array `B` is accessed
while the dynamic indexing of `A` is fine.

#### Example 2.4

```c++
RWBuffer<float> A[10];

struct S {
  RWBuffer<float> B[10];
} s;

[numthreads(4,1,1)]
void main() {
  for (int i = 0; i < 5; i++) {
    A[i][0] = 1.0;
    s.B[i][0] = 1.0; // error: Index for resource array inside cbuffer must be a literal expression
  }
}
```

### Unbound Resource Arrays

Unbound resource arrays are placed in `space0` after the highest explicitly
assigned descriptor, or after the highest implictly assigned descriptor so far,
whichever is greater. They take up the rest of the descriptor slots in `space0`.

#### Example 3.1

```c++
RWBuffer<float> A : register(u1);
RWBuffer<float> B[];     // gets u6 (unbounded range)
RWBuffer<float> C : register(u5);
RWBuffer<float> D[3];    // gets u2 because it fits between A and C but not before A

[numthreads(4,1,1)]
void main() {
  A[0] = D[2][0] + C[0] + B[10][0];
}
```
https://godbolt.org/z/vbvfqjo8h

If there are resources declared after the unbound array that do not fit into the
remaining space available in `space0`, DXC reports an error. For example
increasing the dimension of array 'D' from 3 to 4 results in a `error: resource
D could not be allocated`.

#### Example 3.2
```c++
RWBuffer<float> A : register(u1);
RWBuffer<float> B[];     // gets u6 (unbounded range)
RWBuffer<float> C : register(u5);
RWBuffer<float> D[4];    // error - does not fit in the remaining descriptor ranges in space0 

[numthreads(4,1,1)]
void main() {
  A[0] = D[2][0] + C[0] + B[10][0];
}
```
https://godbolt.org/z/6bYoG599P

It looks like DXC never attempts to assign descriptors from virtual register
space other than `space0`.

However, moving declaration of `D` before the unbounded array `B` compiles
successfully and `B` gets assigned descriptors from `u10` forward.

#### Example 3.3

```c++
RWBuffer<float> A : register(u1);
RWBuffer<float> D[4];    // gets u6
RWBuffer<float> B[];     // gets u10 (unbounded range)
RWBuffer<float> C : register(u5);

[numthreads(4,1,1)]
void main() {
  A[0] = D[2][0] + C[0] + B[10][0];
}
```
https://godbolt.org/z/cjP35n63d

Since DXC seems to only assign descriptors from `space0`, it reports an error
whenever there are two or more unbounded resource arrays in the same register
space.

#### Example 3.4

```c++
RWBuffer<float> C[];  // gets u0 (unbounded range)
RWBuffer<float> D[];  // error

[numthreads(4,1,1)]
void main() {
  D[10][0] = C[20][2];
}
```
https://godbolt.org/z/od7o6xfWE

Unbound resource arrays cannot be placed inside structs and DXC reports `error:
array dimensions of struct/class members must be explicit`.

### Register spaces other than `space0`

Use of other virtual register spaces does not seem to affect the implicit
assignments in `space0`:

#### Example 4.1
```c++
....
RWBuffer<float> A : register(u0, space1); 
RWBuffer<float> B[10];   // gets u0 in space0 (range 10)
RWBuffer<float> C[5][4] : register(u10, space5);
RWBuffer<float> D;       // gets u10 in space0

[numthreads(4,1,1)]
void main() {
  A[0] = D[0] + C[3][3][0] + B[5][0];
}
```
https://godbolt.org/z/EeW17MncE

### Space-only register annotations

DXC supports binding annotations that only specify the register space from which
the descriptor binding should be assigned.

#### Example 5.1

```c++
RWBuffer<float> A : register(u1);        // defaults to space0
RWBuffer<float> B[];                     // gets u2 (unbounded range)
RWBuffer<float> C[3] : register(space1); // gets u0, space1 (range 3)
RWBuffer<float> D : register(space1);    // gets u3, space1

[numthreads(4,1,1)]
void main() {
  A[0] = C[2][0] + D[0] + B[10][0];
}
```
https://godbolt.org/z/3Kc1T3dvs

### Unused resources

Unused resources are resources that are not referenced in the source code or
that are unreachable from the shader entry point function and later removed from
the final IR code by LLVM optimization passes.

When a resource is unused and it has an explicit binding, this binding is
ignored and its descriptor range is available for use by other resources.

In the following example the resources `B`, `C` and `s.D` are identified as
unused and optimized away. Resources `A` and `E` get the binding from descriptor
range originally assigned to `B`:

#### Example 6.1

```c++
struct S {
  RWBuffer<float> D;    
};

RWBuffer<float> A; // gets u0
RWBuffer<float> B[10] : register(u0);  // unused
RWBuffer<float> C : register(u2);      // unused
S s : register(u5);                    // unused
RWBuffer<float> E[5]; // gets u1

void foo() {
    B[2][0] = 1.0;
}

bool bar(int i) {
    return i > 10;
}

[numthreads(4,1,1)]
void main(uint3 gi : SV_GROUPID) {
  if (false) {
    C[0] = 1.0;
  }
  for (int i = 0; i < 5; i++) {
    if (i > 6)
      s.D[0] = 1.0; // unreachable
    if (bar(i))
      foo();        // unreachable
    if (bar(gi.x))
      A[0] = E[2][i];
  }
}
```
https://godbolt.org/z/Mcabxq4jG

Based on resources identified as unused in the example above it is very likely
that DXC is assigning implicit bindings later in the compiler after codegen and
code optimizations.

## Motivation

We need to support implicit resource bindings in Clang as it is a fundamental
part of the HLSL language. 

## Proposed solution

While there are many shaders that explicitly specify bindings for their
resources, a shader without an explicit binding is not at all uncommon. We
should try to match DXC implicit binding behavior in the most common cases
and where it makes sense because debugging resource binding mismatches is not
always straightforward.

### Resources declared directly at global scope
For resources and resource arrays that are declared directly at the global scope
Clang should assign the bindings exactly as DXC does. This is the most common
case and departing from it would be rather impactful breaking change.

That means assigning bindings in `space0` for resources that are identified as
used (i.e. not optimized away) in the order the resources were declared. Arrays
of resources will get the full range of descriptors reserved for them
irrespective of which array elements are accessed, as long as at least of the
array elements it used. Same rules apply if ther resource has a space-only
resource binding, except the binding will be assigned from the specified space
instead of the default `space0`.

### Resources inside user-defined structures and classes

We should consider departure from DXC behavior when a resource or resource array
is declared inside user-defined structure or class. DXC assigns these bindings
based on the order in which the resource is used in the code, which is
impractical and arguably unusable. Any change in the code that reorders the
resource accesses can result in a different binding assignment, and that just
seems wrong (see [Example 2.1](#example-21)).

Additionally, resource arrays inside struct should be treated as arrays and not
as individual resources. The `createHandleFromBinding` calls associated with
resource arrays should reflect the range of the array/descriptors, and the full
range of descriptiors should be reserved, the same was it is reserved for
resource arrays declared at global scope. DXC currently treats these as
individual resources (see [Example 2.2](#example-22)).

There is a chance that this breaks existing user code that relies on the
current DXC behavior, even if it uses only explicit binding (see [Example
2.3](#example-23)). We should re-evaluate the impact of this decision when we
start working on the support of resources in user-defined structs.

### In which part of the compiler should the implicit binding happen

Since the implicing binding assignments need to happen after unused resources
are identified and removed from the code, it needs to happen later in the
compiler after codegen and code optimizations.

If we were to attempt doing it in Sema, we would need to an extensive analysis
to identify all of the resources that are not used, which includes those that
are in unreachable code or internal functions not included in the final shader.
It seems like such analysis would be duplicating the work the existing LLVM
passes are already doing. And it is very likely we would not be able to identify
all of the cases where a resource can be optimized away by LLVM optimization
passes. 

Having the implicit bindings assignments done later in the compiler is probably
also going to be useful once we get to designing DXIL libraries. Unbound
resources exist in library shaders and their bindings get assigned once a
particular entry point is linked to a final shader.

## Detailed design

### Clang Frontend

Unbound resources will be initialized by a resource class constructor for
implicit binding which is described [here](0025-resource-constructors.md#constructor-for-resources-with-implicit-binding).

The `order_id` number will be generated by in `SemaHLSL` class and it will
be used to uniquely identify the unbound resource, and it will also reflect the
order in which the resource has been declared. Implicit binding assignments
depend on the order the resources were declared, so this will help the compiler
to preserve the order. Additionally, it will also help the compiler distinquish
between individual resources with the same type and binding range.

The constructor will call Clang builtin function
`__builtin_hlsl_create_handle_from_implicit_binding` and will pass along all the
arguments provided to the constructor plus the resource handle.

```c++
template <typename T> class RWBuffer<T> {
  RWBuffer(unsigned spaceNo, int range, unsigned index, unsigned orderId, const char *name) {
    __handle = __builtin_hlsl_resource_createhandlefromimplicitbinding(__handle, spaceNo, range, index, orderId, name);
  }  
}
```

### Clang Codegen

The builtin function `__builtin_hlsl_create_handle_from_implicit_binding` will be
translated to LLVM intrinsic `llvm.{dx|spv}.resource.handlefromimplicitbinding`.

The signature of the `@llvm.dx.resource.handlefromimplicitbinding` intrinsic will be:

| Argument | Type |	Description | 
|-|-|-|
| return value | `target()` type|	A handle which can be operated on |
| %order_id | i32 | Number uniquely identifying the unbound resource and declaration order | 
| %space	|	i32 |	Virtual register space |
| %range	|	i32 |	Range size of the binding |
| %index	|	i32	| Index from the beginning of the binding |
| %name	  |	ptr	| Pointer to a global constant string that is the name of the resource |

_Note: We might need to add a uniformity bit here, unless we can derive it from uniformity analysis._

### LLVM Binding Assignment Pass

The implicit binding assignment will happen in two phases - `DXILResourceBindingAnalysis` and `DXILResourceImplicitBindings`.

#### 1. Analysis of available register spaces

A new `DXILResourceBindingAnalysis` will scan the module for all instances of
`@llvm.dx.resource.handlefrombinding` calls and create a map of available
register slots and spaces. The results of the analysis will be stored in
`DXILResourceBindingInfo`.

While the map is being created the analysis can easily detect whether any of the
register bindings overlap, which is something the compiler needs to diagnose.
However, in order to issue a useful error message for this, the analysis would
have to track which register ranges are occupied by which resource. That is
beyond the need of the common case scenario where all bindings are correct and
the analysis just need to figure out the available register slot ranges.

For this reason if the analysis finds that some register bindings overlap, it
will prioritize performance for the common case and just set the
`hasOverlappingBinding` flag on `DXILResourceBindingInfo` to true. The detailed
 error message calculation for the uncommon failure code path will happen later
in `DXILPostOptimizationValidation` pass which can analyze the resource bindings
in more detail and report exactly which resources are overlapping and where. 

This is the same principle that we use when detecting invalid counter usage for
structured buffers as described
[here](0022-resource-instance-analysis.md).

While scanning for the `@llvm.dx.resource.handlefrombinding` calls the analysis
can also take note on whether there are any
`@llvm.dx.resource.handlefromimplicitbinding` calls in the module. If there are,
it will set the `hasImplicitBinding` flag on `DXILResourceBindingInfo` to true.
This will enable the follow-up `DXILResourceImplicitBindings` pass to exit early
if there are no implicit bindings in the module.

_Note: In general diagnostics should not be raised in LLVM analyses or
passes. Analyses may be invalidated and re-ran several times, increasing
performance impact and raising repeated diagnostics. Diagnostics raised after
transformations passes also lose source context resulting in less useful error
messages. However the shader compiler requires certain validations to be done
after code optimizations which requires the diagnostic to be raised from a pass.
Impact is minimized by raising the diagnostic only from a limited set of passes
and minimizing computation in the common case._

#### 2. Assign bindings to implictily bound resource

The implicit binding assignment will happen in an LLVM pass
`DXILResourceImplicitBindings`. The pass will use the map of available register
 spaces `DXILResourceBindingInfo` created by `DXILResourceBindingAnalysis`. It
will scan the module for all instances of
`@llvm.dx.resource.handlefromimplicitbinding` calls, sort them by `order_id`,
and then for each group of calls operating on the same unique resource it will:
- find an available space to bind the resource based on the resource class,
  required range and space
- replace the `@llvm.dx.resource.handlefromimplicitbinding` calls and all of their
uses with `@llvm.dx.resource.handlefrombinding` with the assigned binding

The `DXILResourceImplicitBindings` pass needs to run after all IR optimizations
passes but before any pass that depends on `DXILResourceAnalysis` which relies
on `@llvm.dx.resource.handlefrombinding` calls to exist for all non-dynamically
bound resources used by the shader.

## Alternatives considered (Optional)

## Acknowledgments (Optional)


<!-- {% endraw %} -->
