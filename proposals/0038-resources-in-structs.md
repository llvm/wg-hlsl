---
title: "[0038] - Resources in Structures"
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

This section documents how DXC handles resources that are members of non-static
structs instances declared at the shader global scope, i.e. in the default
`cbuffer` context `$Globals`, and how it handles their register binding.

Additional information about how structs with resources can be used as local
variables, function parameters or static global decls, and their initialization,
assignment, and access behaviors will be added later on.

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
specified register slots. If they do not fit, errors are reported, though the
error messages are not clear and the source location points
to where the resource is first used rather than where it is declared.

```
RWBuffer<float> Buf[10] : register(u4294967293);

[numthreads(4,1,1)]
void main() {
  Buf[0][0] = 0; // line 5
}
```
https://godbolt.org/z/93d317Ej4
```
<source>:5:3: error: Constant values must be in-range for operation.
<source>:5:3: error: Resource handle should returned by createHandle.
<source>:5:13: error: store should be on uav resource.
<source>:5:13: error: buffer load/store only works on Raw/Typed/StructuredBuffer.
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

### Static Structs with Resources

Structs with resources can be declared as static. Same as other statically
declared resources, these struct resource members are not automatically bound.
Instead, the user must explicitly initialize them by assigning an existing
resource to the struct member.

#### Example 11

```
struct M {
  RWBuffer<float> Bufs[10];
};

RWBuffer<float> GlobalBufs[10];

static M m = { GlobalBufs };

[numthreads(4,4,4)]
void main(uint3 ID : SV_GroupID) {
  m.Bufs[ID.y][1] = m.Bufs[ID.x][0];
}
```
https://godbolt.org/z/8fcTfz6d8

Unlike resource arrays in non-static global struct instances, resource arrays
inside static or local struct variables may be dynamically indexable. This is
possible when all resource elements are initialized from a range of the same
dynamically indexable global resource array, as shown in the example above where
`m.Bufs` is initialized from `GlobalBufs`.

### Local variables and Function Parameters

Structs with resources can also be declared as local variables or used as function parameters.

#### Example 12

```
struct N {
  RWBuffer<float> Buf;
};

N n : register(u2);

void foo(N paramN, uint i) {
  paramN.Buf[i] = 10;
}

[numthreads(4,4,4)]
void main(uint3 ID : SV_GroupID) {
  N localN = n;
  localN.Buf[10] = 0.13;
  foo(localN, ID.x);
}
```
https://godbolt.org/z/eKq3jzM5r

### Initialization list

Local or static declarations of structs with resources can be initialized using
initialized lists.

#### Example 13

```
struct P {
  RWBuffer<float> Bufs[4];
};

RWBuffer<float> GlobalBufs[4];

static P p1 = { GlobalBufs };

[numthreads(4,4,4)]
void main(uint3 ID : SV_GroupID) {
  P p2 = { GlobalBufs[3], GlobalBufs[2],
           GlobalBufs[1], GlobalBufs[0]};

  p1.Bufs[ID.y][0] = p2.Bufs[ID.x][0];
}
```
https://godbolt.org/z/zzKe8bjff

### Assignments

Assignment to resource or resource array members of a global non-static structs
is not allowed.

```c++
struct P {
  RWBuffer<float> Buf;
};

P p : register(u2);

RWBuffer<float> GlobalBuf;

[numthreads(4,4,4)]
void main(uint3 ID : SV_GroupID) {
  p.Buf = GlobalBuf; // error
  p.Buf[0] = 10;
}
```
https://godbolt.org/z/f9dd4GYWq

DXC reports an error `cast<X>() argument of incompatible type!`.

### Summary

- DXC supports resources as members of structs, generating global resources
  named after both the struct instance and member.

- Register binding for these resources is determined by explicit `register`
  annotations on the struct instance; if there are no binding annotations,
  resources are implicitly bound in the order they are first referenced, which
  can lead to unpredictable assignments.

- Resource arrays within structs are treated as collections of individual
  resources, with only accessed elements consuming registers. This differs from
  global arrays which reserve the entire range.

- Dynamic (non-constant) indexing into resource arrays or arrays of structs with
  resources is not supported and results in compilation errors.

- Structs may contain multiple resource types, including those inherited or
  nested, with binding rules applied per resource type.

- DXC validates register ranges for global resources but does not check for
  overflow in struct members, which may result in silently overflow.

- Structs with resources can be declared as static or local variables, used as
  function parameters, and initialized with initializer lists.

## Motivation

While resources in structs may not be a widely used HLSL feature, DXC does
support them, and so should the Clang implementation. This also presents an
opportunity to address usability issues, such as the unpredictable implicit
binding order, to make the feature more robust and user-friendly.

## Proposed solution

For each resource or resource array that is a member of a struct declared at
global scope or inside a `cbuffer`, an implicit global variable of the resource
type will be created and associated with the struct instance. All accesses to
the resource member will be redirected to the associated global variable during
Clang CodeGen. 

## Detailed design

### Single Resources

For each resource member of a struct declared at global scope or inside a
`cbuffer`, Clang will create an implicit global variable of the same resource
type. The variable name will be derived from the struct instance name and the
member name, following the naming convention used by DXC (see
[Example 1](#example-1)).

For example, given the following struct definitions and instances:
```c++
struct A {
  RWBuffer<float> Buf;
};

struct B {
  A a;
};

A a1;
B b1 : register(u2);
```

For the resource inside `a1`, Clang will create a global variable of type
`RWBuffer<float>` named `a1.Buf`. For the nested resource in `b1`, accessed via
the member `a`, the global variable will be named `b1.a.Buf`.

When a resource is inherited from a base class, the variable name includes the
base class name as a `::` delimited component. For example:

```c++
struct C : A {
};

C c1;
```

The global variable for the inherited resource in `c1` will be named `c1.A::Buf`.

> **Note:** DXC uses `.` as the delimiter for both base classes and fields,
> which can produce ambiguous names when a field and base class share the same
> name. This ambiguity causes DXC to crash:
> https://godbolt.org/z/5EM418s6T.

### Associated Resource Decl Attribute

To enable efficient lookup of the implicit global variables associated with a
struct instance, a new `HLSLAssociatedResourceDeclAttr` attribute will be
introduced. Each attribute instance holds a pointer to one of the global
resource variables created for the struct. The attribute is attached to the
struct instance declaration, with one attribute per embedded resource or
resource array.

### Resources Arrays

Resource array members of a struct are handled similarly: for each resource
array member, Clang will create a global variable with the same array type.
Unlike DXC, which treats each array element as a separate resource, Clang will
represent the entire array as a single global variable. This approach naturally
supports dynamic indexing of the resource array.

For example:

```c++
struct D {
  RWBuffer<float> Bufs[10];
};

D d1 : register(u5);
```

Clang creates a global variable named `d1.Bufs` of type `RWBuffer<float>[10]`,
with a binding range of `10`.

```
; Resource Bindings:
;
; Name                                 Type  Format         Dim      ID      HLSL Bind  Count
; ------------------------------ ---------- ------- ----------- ------- -------------- ------
; d1.Bufs                               UAV     f32         buf      U0             u5     10
```

### Resources inside Struct Arrays

When a resource (or resource array) is a member of a struct type used in an
array, Clang will create a separate global variable for each array element. The
variable names will be constructed from the struct array instance name, the
array index, and the resource member name, matching DXC's behavior in [Example
4](#example-4). Since the array index is encoded in the resource name, dynamic
indexing of the struct array will not be supported, consistent with DXC.

For example:
```c++
struct A {
  RWBuffer<float> Buf;
};

A array[3];
```

Clang will create three global variables: `array.0.Buf`, `array.1.Buf`, and
`array.2.Buf`.

Indexing the array with a non-constant index produces an error:
`Index for resource array inside cbuffer must be a literal expression.`

### Resource Binding

Each implicit global resource variable will have its own binding attribute
specifying its register binding and whether the binding is explicit or implicit.

When a struct contains multiple resource or resource array members, each one
receives a portion of the binding based on its register class and required
range.

For example:

```c++
struct A {
  RWBuffer<float> Buf;
};

struct E {
  A a;
  RWBuffer<int> array[5];
  StructuredBuffer<uint> SB;
};

E e : register(u2) : register (t5);
```

Clang will create the following global resource declarations:
- `e.a.Buf` of type `RWBuffer<float>` with binding `u2` and range `1`
- `e.array` of type `RWBuffer<int>[5]` with binding `u3` and range `5`
- `e.SB` of type `StructuredBuffer<uint>` with binding `t5`

For implicit binding of resources in structs, Clang will apply the same rules as
for resources declared at global scope:

- Implicit bindings are assigned in declaration order of the resources or
  resource arrays.
- Resource arrays are assigned a contiguous range of register slots matching the
  array size.

This differs from DXC's behavior, which mostly assigns bindings in the order
resources are first used in the shader, though not consistently, making it
unpredictable.

### CodeGen

During Clang CodeGen, any expression that accesses a resource or resource array
member of a global struct instance will be translated to an access of the
corresponding implicit global variable.

#### Single Resource Access

When CodeGen encounters a `MemberExpr` of a resource type, it will traverse the
AST to locate the parent struct declaration, building the expected global
variable name along the way. If the parent is a non-static global struct
instance, CodeGen will search its `HLSLAssociatedResourceDeclAttr` attributes to
find the matching global variable, and then generate IR code to access it.

For example:
```c++
struct A {
  RWBuffer<float> Buf;
};

A a1 : register(u5);

[numthreads(4,1,1)]
void main() {
  a1.Buf[0] = 13.4;
}
```

The `a1.Buf` expression will be translated as access to `@a1.Buf` global
variable, which has been initialized with resource handle from binding at the
shader entry point.

#### Resource Array Element Access

Similarly to a single resource access, when Clang CodeGen sees an
`ArraySubscriptExpr` of a resource or resource array type that is linked to a
`MemberExpr`, it will walk the AST to find its parent struct declaration and the
associated global resource array varible. Then it will generate IR code to
access the array element (or array subset) the same way global resource arrays
are handled.

For example:
```c++
struct B {
  RWBuffer<float> Bufs[4];
};

B b1 : register(u2);
  
[numthreads(4,4,4)]
void main(uint3 ID : SV_GroupThreadID) {
  b1.Bufs[ID.x][ID.y] = 0;
}
```

The expression `b1.Bufs[ID.x]` is translated to a resource handle initialized
from the binding at index `ID.x` within the range of 4 registers starting at
`u2`. The handle is initialized when the array element is accessed, matching
the behavior of global resource arrays.

#### Resource Array Assignment

When an entire resource array is assigned or passed as a function argument,
CodeGen creates a local copy of the array with each element initialized to a
handle from its binding. This matches how global resource array assignments are
handled.

#### Copy of struct with resources

When a struct with resources is assigned to a local variable or passed as a
function parameter, CodeGen creates a local copy. Resource members are
initialized with handle copies from the corresponding global variables, and
resource arrays become local copies with each element initialized to a handle
from its binding.

Note that structs declared at global scope reside in constant address space `2`
and use `cbuffer` struct layout. Copying these structs requires HLSL-specific
handling (see
[llvm/llvm-project#153055](https://github.com/llvm/llvm-project/issues/153055)),
and support for copying embedded resources and resource arrays must be built on
top of that.

#### Binding Range Validation

Clang will detect out-of-range bindings during semantic analysis and report
clear error messages pointing to the resource declaration. This improves upon
DXC's range validation errors, which are often unclear and sometimes missing
entirely.

#### Specifying `space` for resources in structs

Clang will support specifying register `space` for struct instances containing
resources, addressing a limitation in DXC (see [Example 10](#example-10)).

## Alternatives considered (Optional)

## Acknowledgments (Optional)
