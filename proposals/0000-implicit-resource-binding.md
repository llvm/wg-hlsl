* Proposal: [NNNN](NNNN-implicit-resource-binding.md)
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
 to. For simple resources that is the only descriptor the resource needs. In
 case of arrays the `register` specifies the start of the description range
 needed for the resource array. The dimensions of the array determine the size
 of the description range.

The annotation can also include virtual register space:

```c++
Texture2D<float4> Tx : register(t3, space1); 
```

_Note: See the HLSL Language specification section Resource Binding for more
details._

Specifying resource binding on a resource is not mandatory. If a binding is not
provided by the user, it is up to the compiler to assign a descriptor to such
resource. This is called _implicit resource binding_ and it is the focus of this
document.

## Current behavior in DXC

This section documents the implicit resource binding assignment in DXC. For
simplicty the examples below use the just the `u` registers and
`RWBuffer<float>` resource, but same binding assignment rules apply to other
register and resource types as well.

### Simple Resource Declarations
 Resource without binding assignment that are declared directly at the global
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
assigned in the order they are referenced in the code, and not the order in
which they were declared:

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
(max. value of 32-unsigned integer).

### Constant-size Resource Arrays

Constant-size resource arrays declared directly at the global scope are also
processed in the order they appear in the source code. They are assigned the
first range of available decriptors in `space0` that fits the array size
regardless of whether the individual resources in the array are used or not, as
long as at least one of the them is accessed.

If none of the resources in the are used, the whole resource declaration is
optimized away and its descriptor range is available for use by other resources.

#### Example 2.1
```c++
RWBuffer<float> A : register(u2);
RWBuffer<float> B[4];    // gets u3 because it does not fit before A (range 4)
RWBuffer<float> C[2];    // gets u0 because it fits before A (range 2)
RWBuffer<float> D[50] : register(u6); // unused
RWBuffer<float> E[2];    // gets u7 which is right after B (range 4)

[numthreads(4,1,1)]
void main() {
  A[0] = E[2][0] + C[1][0] + B[1][0];
}
```
https://godbolt.org/z/qha84sjvT

However, if the resource array is defined in a `struct`, the binding seems to be
assigned to the individual array elements in the order they are used in the
code. In other words, the array elements are treated as unrelated individual
resources:

#### Example 2.2
```c++
struct S {
    RWBuffer<float> B[4]; // s.B.2 gets u3
    RWBuffer<float> C[2]; // s.C.1 gets u1
    RWBuffer<float> E[2]; // s.E.2 gets u0
};                        // s.E.1 gets u4


RWBuffer<float> A : register(u2);
S s;

[numthreads(4,1,1)]
void main() {
  A[0] = s.E[2][0] + s.C[1][0] + s.B[3][0] + s.E[1][0];
}
```
https://godbolt.org/z/45j8aqTaf

This seems wrong. Resource arrays should be bound to a continuous description
range and the range should be reflected in the `createHandleFromBinding`
arguments. It also makes the binding susceptible to change whenever the code
changes and is not something that can be relied upon. 

Array resources inside structs are also not allowed to use dynamic indexing. In
the following example DXC reports error when the resource array `B` is accessed
while the dynamic indexing of `A` with is fine.

#### Example 2.3

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
RWBuffer<float> D[3];    // gets u2 because it first between A and C but not before A

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

It looks like DXC never attempts to assing descriptors from virtual register
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

Since DXC seems to only assigns descriptors from `space0`, it reports error
whenever there are:
- two or more unbound resource arrays without explicit binding
- one unboud resource array with explicit binding in `space0` and one or more
  unbound resource arrays without explicit binding

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

DXC support binding annotations that only specify the register space from which the descriptor binding should be assigned.

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

Unbound resources will be initialized by a resource class constructor that takes
3 arguments - the `space`, `range` and `index`. This constructor will be
declared in `HLSLExternalSemaSource` as part of resource class setup.

The arguments specify the virtual register space (defaulting to 0),
required descriptor range and an index of the resource in the range. 

The constructor will call Clang builtin function
`__builtin_hlsl_create_handle_from_implicit_binding` and will pass along the
`space`, `range` and `index` values, and it will also include the uninitialized
resource handle. The type of the handle argument will be used to infer the
specific resource handle type returned by the buildin function. This will happen
in `SemaHLSL::CheckBuiltinFunctionCall` the same way we infer return types for
HLSL intrinsic builtins based on the builtin arguments.

```c++
template <typename T> class RWBuffer<T> {
  RWBuffer(unsigned space, int range, unsigned index) {
    __handle = __builtin_hlsl_create_handle_from_implicit_binding(__handle, space, range, index);
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

_Note: We might need to add a uniformity bit here, unless we can derive it from uniformity analysis._

The `order_id` number will be generated by Clang Codegen in `GCHLSLRuntime`. It
will be used to uniquely identify the unbound resource, and it will also reflect
the order in which the resource has been declared. Implicit binding assignments
depend on the order the resources were declared, so this will help the compiler
to preserve the order. Additionally, it will also help the compiler distinquish
between individual resources with the same type and binding range.

### LLVM Binding Assignment Pass

The implicit binding assignment for DirectX will happen in an LLVM pass
`DXILResourceImplicitBindings`. The pass will run after all IR optimizations and
will use the results of `DXILResourceBindingAnalysis`. It needs to run before
any other pass that uses this analysis because it will be updating it with the
newly assigned bindings.

The pass will scan the module to gather all instances of
`@llvm.dx.resource.handlefromimplicitbinding` calls and sort them by
`%order_id`. Then it will process the list sequentially based on the
`%order_id`, and for each group of calls operating on the same unique resource
it will find an available resource binding based on the required resource class,
range and space. It will then replace all of the
`@llvm.dx.resource.handlefromimplicitbinding` calls and all of its uses with new
`@llvm.dx.resource.handlefrombinding` calls and add the new binding to the
`DXILResourceBindingAnalysis` map. 

## Alternatives considered (Optional)

## Acknowledgments (Optional)


<!-- {% endraw %} -->
