<!-- {% raw %} -->

# Allowing multiple address spaces for the `this` pointer

*   Proposal: [NNNN](http://NNNN-this-address-space.md)
*   Author(s): [Nathan Gauer](https://github.com/keenuts),
    [Steven Perron](https://github.com/s-perron)
*   Status: **Design In Progress**

*During the review process, add the following fields as needed:*

*   PRs: [\#111](https://github.com/llvm/wg-hlsl/pull/111),
    [llvm-project:\#127675](https://github.com/llvm/llvm-project/pull/127675)
*   Issues:
*   Posts:

## Introduction

HLSL uses copy-in/copy-out semantics for parameter passing. This requires that
the pointer passed to the callee points to the default address space and
directly to a variable. This simplifies code generation for the callee, as there
is only one address space for the parameter. It also ensures that the SPIR-V
restriction that pointer operands must be memory object declarations is true.

However, this is not the case for the 'this' pointer on member functions. The
HLSL specification states that the 'this' pointer is a reference to the object,
which means that it could be a pointer to any address space and could point to
an object that is a member of another object.

## Motivation

HLSL allows member functions. In HLSL, the this pointer is a reference to the
object on which it was called. From the user perspective, the same function is
called regardless of the address space of the object on which it is called. The
user does not have to write a version of the function for each address space.

This is implemented in DXC, and the same behavior must be implemented in Clang.
So far, this has not been a problem because no address space other than the
default address space has been used until recently. This problem will be exposed
when the hlsl\_device and hlsl\_constant address spaces are used.

Consider this example:

```c
struct S {
  int a;
  int add(int v) { return a+v; }
};

cbuffer B : register(b1) {
  S s;
};

RWBuffer<int> o : register(u0);

[numthreads(1,1,1)]
void main()
{
  o[0] = s.add(3);
}
```

Once
[https://github.com/llvm/llvm-project/pull/124886](https://github.com/llvm/llvm-project/pull/124886),
lands, this example fails with the error:

```
t.hlsl:15:10: error: cannot initialize object parameter of type 'S' with an expression of type 'hlsl_constant S'
   15 |   o[0] = s.add(3);
```

## Proposed solution

All HLSL address spaces will be made a subspace of a new hlsl\_generic address
space. The \`this\` pointer will point to data within this address space. This
allows an address space cast to be inserted on the actual parameter by Clang and
the member function to be called.

These address space casts cause issues for SPIR-V because SPIR-V’s Generic
storage class is not allowed by the Vulkan environment for SPIR-V, and a pointer
cannot be cast from one storage class to another. The address space casts will
be removed through optimizations and a fix-up pass.

All calls to member functions will be inlined, even if the function is marked as
noinline. Once inlined, a pass that will propagate the address space before the
cast to all uses of the address space cast can be run.

This solution has been used before. It is essentially the same solution used in
DXC to generate SPIR-V code. The fix-up pass would be similar to the
FixStorageClass pass. This solution should work for SPIR-V. C++ for OpenCL uses
a generic address space in the same way. The OpenCL environment for SPIR-V
allows address space casts to generic, so no fix-up pass is required.

The disadvantage of this solution is that some error checking is not possible
until after optimizations have been run. For example, the compiler will not be
able to check that the pointer for the InterlockedAdd is valid until after
inlining. See

```
struct S
{
    int a;
    int atomicAdd() {
        int o;
        InterlockedAdd(a, 1, o);
        return o;
    }
};

RWBuffer<float> b;

[numthreads(1, 1, 1)]
void computeMain()
{
    S str;
    int a = str.atomicAdd();
    b[0] = a;
}
```

It is important to note that these problems will become increasingly complex if
future versions of HLSL add references with explicit address spaces and
functions that can be overloaded based on the address space. Should that occur,
reevaluation of this solution may be necessary.

## Alternatives considered

### Make the `this` parameter implicitly `inout`

An alternative solution is to create a copy of the object on which the member
function is being called, similar to the handling of other parameters. However,
this approach necessitates special handling of the copy assignment operator to
prevent an infinite recursion of temporary objects. The copying in and out at a
call site are managed as if the assignment operator was employed; however, this
is a function call with a "this" pointer, which requires the same treatment.

Furthermore, this solution introduces a discrepancy between the behavior and the
specification, as well as potential inconsistencies with DXC. The aforementioned
example with the atomic operation illustrates this issue. If a copy-in and
copy-out operation is implemented for "str," the accesses to "str" are no longer
atomic.

### Automatically replicate member functions for each address space

An additional potential solution is to duplicate the member function for each
address space. This could be implemented in two ways. The first is to have
multiple versions of the struct, one for each address space. This would be
similar to adding an implicit template for the address space to the struct. The
second is to have one struct type, but have multiple member functions. This is
similar to having an implicit template on each member function for the address
space.

Both of these options would have to be implemented during sema. The issue is
that both of these solutions appear to be significantly different than anything
currently done in sema. Although I believe it is possible, I am uncertain if we
should invent a novel process.

<!-- {% endraw %} -->
