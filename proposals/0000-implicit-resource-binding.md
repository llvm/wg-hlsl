* Proposal: [NNNN](NNNN-implicit-resource-binding.md)
* Author(s): [Helena Kotas](https://github.com/hekota)
* Status: **Design In Progress**

## Introduction

HLSL Resources are runtime-bound data that are provided as input, output, or
both to shader programs. Resources need to be bound to the graphics or compute
pipeline for shaders to access them. In DirectX this is done via descriptors,
which are sometimes referred to as views or handles.

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
register and resource types.

### Simple Resource Declarations
Unbound resources are processed in the order they appear in the code. They are
assigned the first available register slot (or range) in `space0` where the
resource fits. Unused resources are optimized away and do not participate in the
implicit binding assignment.

#### Example 1
```c++
RWBuffer<float> A : register(u0);
RWBuffer<float> B;                 // gets u1
RWBuffer<float> C: register(u2);   // unused
RWBuffer<float> D;                 // gets u2

[numthreads(4,1,1)]
void main() {
  A[0] = B[0] + D[0]; // all resources except C are used
}
```

If `C` is used then `D` gets assigned descriptor `u3`. 

### Resource Arrays

Constant-sized resource arrays are assigned a range of descriptors regardless of
whether the individual resources in the array are used or not. If none of the
resources are used though the whole resource declaration is optimized away and
its descriptor range is available for use by other resources.

#### Example 2
```c++

RWBuffer<float> A : register(u2);
RWBuffer<float> B[4];                 // gets u3 because it does not fit before A (range 4)
RWBuffer<float> C[2];                 // gets u0 because it fits before A (range 2)
RWBuffer<float> D[50] : register(u6); // unused - no register assignment
RWBuffer<float> E[2];                 // gets u7 which is right after B (range 4)

[numthreads(4,1,1)]
void main() {
  A[0] = B[2][0] + C[1][0] + E[1][0]; // all resources except D are used
}
```

### Unboud Resource Arrays

Unbound resources are placed in `space0` after the highest explicitly assigned
descriptor, or after the highest implictly assigned descriptor so far, whichever
is greater. They take up the rest of the descriptor slots in `space0`.

If there are resources declared after the unbound array that do not fit into the
remaining space available in `space0`, DXC reports an error.

#### Example 3

```c++
// assume all resources are used
RWBuffer<float> A : register(u2);
RWBuffer<float> B[];               // gets u6 (unbounded range)
RWBuffer<float> C;                 // gets u0 because it fits before A
RWBuffer<float> D : register(u5);
```

#### Example 4
DXC reports `error: resource E could not be allocated`:
```c++
// assume all resources are used
RWBuffer<float> A : register(u2);
RWBuffer<float> B[];               // gets u6 (unbounded range)
RWBuffer<float> C;                 // gets u0 because it fits before A
RWBuffer<float> D : register(u5);
RWBuffer<float> E[10];             // error - does not fit before A
```

It looks like DXC never attempts to assing descriptors from virtual register
space other than `space0`.

#### Example 5
Moving declaration of `E` before `B` compiles successfully and `B` gets assigned
descriptor `u13`:
```c++
// assume all resources are used
RWBuffer<float> A : register(u2);
RWBuffer<float> D[10];             // gets u3 (range 10)
RWBuffer<float> B[];               // gets u13 (unbounded range)

[numthreads(4,1,1)]
void main() {
  A[0] = B[2][0] + D[1][0];
}
```

#### Example 6
Since DXC seems to only assigns descriptors from `space0`, it reports error when
there are:
- two or more unbound resource arrays without explicit binding
- a resource array with explicit binding in `space0` and one unbound resource
  array

```c++
// assume all resources are used
RWBuffer<float> C[];  // gets u0
RWBuffer<float> D[];  // error
```

### Register spaces other than `space0`

Use of other virtual register spaces does not seem to affect the implicit
assignments in `space0`:

#### Example 7
```c++
// assume all resources are used
RWBuffer<float> A : register(u0, space1); 
RWBuffer<float> B[10];   // gets u0 in space0 (range 10)
RWBuffer<float> C[5][4] : register(u10, space5);
RWBuffer<float> D;       // gets u10 in space0
```

### Miscelanious Notes

The maximum register slot or virtual space number is `UINT_MAX` (max. value of
32-unsigned integer).

## Motivation

We need to support implicit resource bindings in Clang as it is a fundamental
part of the HLSL language. 

## Proposed solution

TBD

## Detailed design

## Alternatives considered (Optional)

## Acknowledgments (Optional)


<!-- {% endraw %} -->
