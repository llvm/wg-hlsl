---
title: "[0025] - Resource Initialization and Constructors "
params:
  status: Design In Progress
  authors:
    - hekota: Helena Kotas
---

## Introduction

HLSL resource classes are represented in Clang as struct types, or template
struct types with the resource element type as the template argument. The
resource structs have a member field `__handle` of type `__hlsl_resource_t` that
is decorated with type attributes specifying the resource class, contained type,
whether it is a handle for a raw buffer or ROV, and other properties. These
builtin types are constructed in `HLSLExternalSemaSource`.

For example, the source code for `RWBuffer<T>` would look like this:

```c++
template <typename T> struct RWBuffer {
private:
  using handle_t = __hlsl_resource_t
      [[hlsl::contained_type(T)]] [[hlsl::resource_class(UAV)]];
  handle_t __handle;
};
```
_* The resource declaration also includes element type validation via C++20
concepts which I have not included here for readability._

Depending on the resource type its definition will include methods for accessing
or manipulating the resource, such as subscript operators, `Load` and `Store`
methods, etc.

Note that while the HLSL resources are defined as structs, they are often
referred to as _resource classes_, _resource records_, or _resource structs_.
These terms can be used interchangeably.

The record classes can be declared at the global scope, used as function in/out
parameters, or as local variables. They need to be properly initialized
depending on the declaration scope, and this should be done by static
initialization methods and resource class constructors.  

## Proposed solution

Each resource class will have a set of static initialization methods that will
initialize the resource handle based on its binding  - whether it is explicit,
implicit, or dynamic. 

Each resource class should also have a default constructor, a copy constructor
and an assignment operator that will take care of initialization of local
resource instances, for example when an existing resource is assigned to a local
resource variable.

### Resources with explicit binding

Resources declared at the global scope that have an explicit binding will be
initialized by the following static method:

```c++
template <typename T> struct RWBuffer {
  ...
public:
  // Create method for resources with explicit binding.
  static RWBuffer<T> __createFromBinding(unsigned registerNo, unsigned spaceNo, int range, unsigned index, const char *name) {
    RWBuffer<T> tmp;
    tmp.__handle = __builtin_hlsl_resource_handlefrombinding(tmp.__handle, registerNo, spaceNo, range, index, name);
    return tmp;
  }
  ...
};
```

The `tmp.__handle` argument passed into the
`__builtin_hlsl_resource_handlefrombinding` Clang builtin function will be used
to infer the return type of that function. This is the same way we infer return
types for HLSL intrinsic builtins based on their arguments, except in the case
only the type of the argument is used and not its value (which is
uninitialized, or set to `poison` value).

The `name` argument will be used to generate the DXIL resource metadata and also
for resource diagnostics that need to happen after optimizations later in the
compiler pipeline.

A call to this initialization method will be created by Sema as part of
uninitialized variable declaration processing (`Sema::ActOnUninitializedDecl`).
It will work as if it would replace:

`RWBuffer<float> A : register(u3);`

with

`RWBuffer<float> A = RWBuffer<float>::__createFromBinding(3,0,1,0,"A");`.

An alternative considered was to have a resource class constructor that accepts
an initialized handle, which would be invoked by the static initialization
methods rather than setting the handle value directly. However, this approach is
not feasible because `__hlsl_resource_t` is translated to an LLVM target type
`(target("dx.*", ...))` and marked with the `IsTokenLike` property to prevent
unwanted LLVM optimizations on resource handles. As a result, these types can
only be used as arguments to LLVM intrinsics, not as parameters to regular
functions or methods. Therefore, it is not possible to implement a constructor
(or any function) that takes a handle type argument.

### Resources with implicit binding

If a resource does not have an explicit binding annotation, or if it has an
annotation that only specifies the virtual register space, it has _implicit
binding_. The actual binding will be assigned later on by the compiler.

Resources with implicit binding will be initialized by the following static
method:

```c++
template <typename T> struct RWBuffer {
  ...
public:
  // Create method for resources with implicit binding.
  static RWBuffer<T> __createFromImplicitBinding(unsigned orderId, unsigned spaceNo, int range, unsigned index, const char *name) {
    RWBuffer<T> tmp;
    tmp.__handle = __builtin_hlsl_resource_handlefromimplicitbinding(tmp.__handle, spaceNo, range, index, orderId, name);
    return tmp;
  }
  ...
};
```

The `tmp.__handle` argument passed into the
`__builtin_hlsl_resource_handlefromimplicitbinding` Clang builtin function
will be used to infer the return type of that function.

The `orderId` number will be generated in the `SemaHLSL` class and will be
used to uniquely identify the unbound resource, as well as reflect the order in
which the resource has been declared. It will be used later on in the
compiler to assign implicit bindings to resources in the right order.

The `name` argument will be used to generate the DXIL resource metadata and also
for resource diagnostics that need to happen after optimizations later in the
compiler pipeline.

A call to this initialization method will be created by Sema as part of
uninitialized variable declaration processing (`Sema::ActOnUninitializedDecl`).
It will work as if it would replace:

`RWBuffer<float> A;`

with

`RWBuffer<float> A = RWBuffer<float>::__createFromImplicitBinding(0,0,1,0,"A");`.

Or if the resource has a space-only binding annotation, it will work as if it
would replace:

`RWBuffer<float> A : register(space13);`

with

`RWBuffer<float> A = RWBuffer<float>::__createFromImplicitBinding(0,13,1,0,"A");`.

### Resources with dynamic binding

TBD

### Default constructor

Default constructor does not take any arguments and will initialize the
`__handle` member to a `poison` value, which means that its value is undefined.
This constructor will be used for resources that are declared as local
variables.

```c++
template <typename T> struct RWBuffer {
  ...
public:
  // Constructor for uninitialized handles.
  RWBuffer() {
    __handle = __builtin_hlsl_resource_uninitializedhandle(__handle);
  }
  ...
};
```

The `__handle` argument of the `__builtin_hlsl_resource_uninitializedhandle` Clang
builtin function will be used to infer the return type of that function.

A call to the default resource constructor is automatically generated by Clang
for any uninitialized resource class. For resources declared at global scope
Sema analysis will set the initialization expression to use a different
constructor based on whether the resource has an explicit binding or not.

### Copy constructor and assignment operator

The copy constructor and the assignment operator will be explicitly defined
to assign the handle from one instance of a resource class to another. 

Note: If we used the default implementation (marking them with `= default;`),
Clang would translate them into `memcpy` intrinsic calls instead of assignment
of a handle. This would make optimizations more complicated since `memcpy` is
often turned into a load and store of an `i32`/`i64`.

```c++
template <typename T> struct RWBuffer {
  ...
public:
  // Resources are copyable.
  RWBuffer(RWBuffer &LHS) {
    __handle = RHS.__handle;
  };

  // Resources are assignable.
  RWBuffer &operator=(RWBuffer &LHS) {
    __handle = RHS.__handle;
    return *this;
  }
  ...
};
```

### Summary

```c++
template <typename T> struct RWBuffer {
private:
  using handle_t = __hlsl_resource_t
      [[hlsl::contained_type(T)]] [[hlsl::resource_class(UAV)]];
  handle_t __handle;

public:
  // Create method for resources with explicit binding.
  static RWBuffer<T> __createFromBinding(unsigned registerNo, unsigned spaceNo, int range, unsigned index, const char *name) {
    handle_t h = __builtin_hlsl_resource_handlefrombinding(h, registerNo, spaceNo, range, index, name);
    return RWBuffer<T>(handle);
  }

  // Create method for resources with implicit binding.
  static RWBuffer<T> __createFromImplicitBinding(unsigned orderId, unsigned spaceNo, int range, unsigned index, const char *name) {
    handle_t h = __builtin_hlsl_resource_handlefromimplicitbinding(h, spaceNo, range, index, orderId, name);
    return RWBuffer<T>(handle);
  }

  // Public constructor for uninitialized handles.
  RWBuffer() {
    __handle = __builtin_hlsl_resource_uninitializedhandle(__handle);
  }

  // Resources are copyable.
  RWBuffer(RWBuffer &LHS) = default;

  // Resources are assignable.
  RWBuffer &operator=(RWBuffer &LHS) = default;
  ...
};
```

## Alternatives considered (Optional)

## Acknowledgments (Optional)

Chris Bieneman
