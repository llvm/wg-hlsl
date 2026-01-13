---
title: "[NNNN] - Resources in Structures"
params:
  status: Design In Progress
  authors:
    - hekota: Helena Kotas
---

## Introduction

HLSL resources are runtime-bound data objects supplied to shader programs as
input, output, or both. While they are typically declared as global variables of
specific resource types at the shader's global scope, resources can also be
members of user-defined structures or classes. For brevity, this document refers
to user-defined structures and classes simply as _structs_.

Register binding for resources in structs is specified on the struct instance
declaration. It cannot be specified directly on the struct's resource members
because multiple instances of the same struct could have conflicting bindings.

## Current Behavior in DXC

This section documents how DXC handles resources declared as members of structs
and theirs bindings.

### Struct with a Single Resource

#### Example 1
```c++
struct A {
  RWBuffer<float> Buf;
};

A a1 : register(u5);
A a2;
  
[numthreads(4,1,1)]
void main() {
  a1.Buf[0] = a2.Buf[0];
}
```
https://godbolt.org/z/bPE7Gcafc

For this shader DXC creates 2 global resources named `a1.Buf` and `a2.Buf`,
based on the name of the struct instance. `a1.Buf` is bound to register `u5` as
specified by the register annotation. `a2` does not have any binding annotation
and will be implicitly bound to `u0`.

```
; Resource Bindings:
;
; Name                                 Type  Format         Dim      ID      HLSL Bind  Count
; ------------------------------ ---------- ------- ----------- ------- -------------- ------
; a1.Buf                                UAV     f32         buf      U0             u5     1
; a2.Buf                                UAV     f32         buf      U1             u0     1
```

### Struct with a Resource Array

#### Example 2
```c++
struct B {
  RWBuffer<float> Bufs[10];
};

B b1 : register(u2);
B b2;
  
[numthreads(4,1,1)]
void main() {
  float x = b2.Bufs[7][0];
  float y = b2.Bufs[2][0];
  float z = b2.Bufs[1][0];
  
  b1.Bufs[0][0] = x + y + z;
}
```
https://godbolt.org/z/3TGz8dW38

DXC creates a named global resource for each accessed element of the resource
array. The resource name is constructed from the struct instance name, the array
member name, and the array index: `b1.Bufs.0`, `b2.Bufs.7`, etc.

This implies that DXC treats each element of a resource array within a struct as
an individual resource rather than as a range of resources. In the Resource
Binding table each of these has a `Count` of `1` and a separate named entry.
This differs from global-scope resource arrays, which are represented as a
single named global resource with `Count` set to its range size.

When a struct instance has an explicit binding annotation, the resource array
members are bound to consecutive register slots starting from the specified
register. Unused array elements do not consume register slots, making them
available for use by other resources. This again differs from global-scope
resource arrays, which reserve the entire register range regardless of whether
all array elements are used.

Resource array elements without explicit binding information are bound to
available register slots **in the order they are referenced in the shader
code**. For example, `b2.Bufs[7]` is accessed first and gets assigned register
`u0`, while `b2.Bufs[2]` is accessed later and gets `u1`.

```
; Resource Bindings:
;
; Name                                 Type  Format         Dim      ID      HLSL Bind  Count
; ------------------------------ ---------- ------- ----------- ------- -------------- ------
; b1.Bufs.0                             UAV     f32         buf      U0             u2     1
; b2.Bufs.7                             UAV     f32         buf      U1             u0     1
; b2.Bufs.2                             UAV     f32         buf      U2             u1     1
; b2.Bufs.1                             UAV     f32         buf      U3             u3     1
```

### Dynamic Indexing of Resource Arrays

DXC does not support dynamic indexing of resource arrays that are members of
structs. Attempting to use a non-constant index produces the error: `Index for
resource array inside cbuffer must be a literal expression`. The error mentions
`cbuffer` because all declarations at a global scope are technically in a global
`cbuffer` scope named `$Globals`.

#### Example 3
```
struct C {
  RWBuffer<float> Bufs[10];
};

C c;
  
[numthreads(4,4,4)]
void main(uint3 ID : SV_GroupID) {
  c.Bufs[ID.y][1] = c.Bufs[ID.x][0];
}
```
https://godbolt.org/z/c9aPoE943
```
<source>:9:3: error: Index for resource array inside cbuffer must be a literal expression
  c.Bufs[ID.y][1] = c.Bufs[ID.x][0];
  ^
```

### Arrays of Structs with Resources

#### Example 4

```
struct A {
  RWBuffer<float> Buf;
};

A d[10] : register(u5);
A e[50];
  
[numthreads(4,1,1)]
void main(uint3 ID : SV_GroupID) {
  float x = d[2].Buf[1];
  float y = e[7].Buf[0];
  float z = e[1].Buf[0];

  d[5].Buf[0] = x + y + z;
}
```
https://godbolt.org/z/xcKcdeKzc

As in the previous examples, DXC creates a named resource for each accessed
resource element. The resource name is constructed from the struct array
instance name, the array index, and the resource member name: `d.2.Buf`,
`e.7.Buf`, etc.

Resources inside struct arrays with explict binding get assigned to register
slots based on the `register` annotation and the array index. So since `d` has
`register(u5)`, the individual resource inside the struct at `d[2]` gets
register `u7` (`5 + 2 = 7`) and the one in `d[5]` gets `u10` (`5 + 5 = 10`).

Implicitly bound resources inside struct arrays are bound to available
register slots **in the order they are first referenced in the shader code**.
For example, `e[7].Buf` is bound to `u0` and `e[1].Buf` is bound to `u1` because
`e[7].Buf` is accessed first in the shader.

```
; Resource Bindings:
;
; Name                                 Type  Format         Dim      ID      HLSL Bind  Count
; ------------------------------ ---------- ------- ----------- ------- -------------- ------
; d.2.Buf                               UAV     f32         buf      U0             u7     1
; d.5.Buf                               UAV     f32         buf      U1            u10     1
; e.7.Buf                               UAV     f32         buf      U2             u0     1
; e.1.Buf                               UAV     f32         buf      U3             u1     1
```

### Dynamic Indexing of Struct Arrays with Resources

If a resource is a member of a struct that is in an array, DXC does not support
accessing this resource with non-constant index into the struct array.
Attempting to do so produces an error.

#### Example 5
```
struct D {
  RWBuffer<float> Buf;
};

D arrayOfD[10];
  
[numthreads(4,4,4)]
void main(uint3 ID : SV_GroupID) {
  arrayOfD[ID.y].Buf[0] = 1.0f;
}
```
https://godbolt.org/z/cnz1oe7rx
```
<source>:9:3: error: Index for resource array inside cbuffer must be a literal expression
  arrayOfD[ID.y].Buf[0] = 1.0f;
  ^
```

### Inheritance and Multiple Resources Kinds

A single struct can contain multiple resources of different types. Resource
members can also be inherited from a base class or nested within member structs.
Bindings for these various resource types is specified using multiple `register`
annotations on the struct instance. All resources of the same type share the
same base register and are bound sequentially starting from that register in the
order they are declared.

#### Example 6
```
class E {
  RWBuffer<float> UavBuf1;
};

class F {
  StructuredBuffer<int> SrvBuf1;
};


class G : F {
  E e;
  StructuredBuffer<int> SrvBuf2;
  RWBuffer<float4> UavBufs2[4];
};

G g : register(u5) : register(t3);

[numthreads(4,4,4)]
void main(uint3 ID : SV_GroupID) {
  float x = g.e.UavBuf1[0];
  float y = g.SrvBuf1[0];
  float z = g.SrvBuf2[0];
  float w = g.UavBufs2[3][0].x;

  g.UavBufs2[1][0] = float4(x, y, z, w);
}

```
https://godbolt.org/z/EsbhfWYGG

All of the resources have explicit binding and the Resource Bindings table looks like this:

```
; Resource Bindings:
;
; Name                                 Type  Format         Dim      ID      HLSL Bind  Count
; ------------------------------ ---------- ------- ----------- ------- -------------- ------
; g.F.SrvBuf1                       texture  struct         r/o      T0             t3     1
; g.SrvBuf2                         texture  struct         r/o      T1             t4     1
; g.UavBufs2.3                          UAV     f32         buf      U0             u9     1
; g.UavBufs2.1                          UAV     f32         buf      U1             u7     1
; g.e.UavBuf1                           UAV     f32         buf      U2             u5     1
```

#### Example 7

If we remove the `register` annotations on the `G` instance in [Example
6](#example-6), its resources are bound **mostly in the order they are first
referenced in the shader**. However, the resource inside class `E` is assigned
the highest UAV register slot (indicating it was bound last), despite being
referenced first. This inconsistency demonstrates that implicit register
assignment for resources within structs lacks a predictable ordering rule.
```
// Using same struct declarations as in Example 6.

G g_impl;

[numthreads(4,4,4)]
void main(uint3 ID : SV_GroupID) {
  float x = g_impl.e.UavBuf1[0];
  float y = g_impl.SrvBuf1[0];
  float z = g_impl.SrvBuf2[0];
  float w = g_impl.UavBufs2[3][0].x;

  g_impl.UavBufs2[1][0] = float4(x, y, z, w);
}
```
https://godbolt.org/z/3TW565acT
```
; Name                                 Type  Format         Dim      ID      HLSL Bind  Count
; ------------------------------ ---------- ------- ----------- ------- -------------- ------
; g_impl.F.SrvBuf1                  texture  struct         r/o      T0             t0     1
; g_impl.SrvBuf2                    texture  struct         r/o      T1             t1     1
; g_impl.UavBufs2.3                     UAV     f32         buf      U0             u0     1
; g_impl.UavBufs2.1                     UAV     f32         buf      U1             u1     1
; g_impl.e.UavBuf1                      UAV     f32         buf      U2             u2     1
```

### Binding range validation

#### Example 8

For resources declared at global scope, DXC validates that they fit within the
specified register slots. If they do not fit, an error is reported during
validation, though the error message is cryptic and the source location points
to where the resource is first used rather than where it is declared.

```
RWBuffer<float> Buf[10] : register(u4294967293);

[numthreads(4,1,1)]
void main() {
  Buf[0][0] = 0;
}
```
https://godbolt.org/z/93d317Ej4
```
<source>:12:3: error: Constant values must be in-range for operation.
```

#### Example 9

For resources declared within a struct, DXC does not validate whether they fit
within the specified register space. If they do not fit, the register slot
silently overflows.

```
struct H {
    RWBuffer<float> Bufs[10];
    RWBuffer<float> OneBuf;
};

H h : register(u4294967290);

[numthreads(4,1,1)]
void main() {
  h.Bufs[7][0] = 0;
  h.OneBuf[0] = 0;
}
```
https://godbolt.org/z/jcMfa3TaE

```
; Resource Bindings:
;
; Name                                 Type  Format         Dim      ID      HLSL Bind  Count
; ------------------------------ ---------- ------- ----------- ------- -------------- ------
; h.Bufs.7                              UAV     f32         buf      U0             u1     1
; h.OneBuf                              UAV     f32         buf      U1             u4     1
```

### Register Spaces

#### Example 10

DXC does not allow specifying a register space on a struct instance (which is
technically part of the default constant buffer), even though the register
annotation applies to the resource inside the struct and not the struct itself.
Attempting to do so produces an error.

```
struct K {
    RWBuffer<float> Buf;
};

K k : register(u3, space0);

[numthreads(4,1,1)]
void main() {
  k.Buf[0] = 0;
}
```
https://godbolt.org/z/Mo8Paoq7G
```
<source>:5:7: error: register space cannot be specified on global constants.
```

## Motivation

We need to support this in Clang.

## Proposed solution

## Detailed design

## Alternatives considered (Optional)

## Acknowledgments (Optional)
