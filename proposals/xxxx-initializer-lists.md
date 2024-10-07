<!-- {% raw %} -->

# Initializer Lists

* Proposal: [NNNN](NNNN-initializer-lists.md)
* Author(s): [Chris Bieneman](https://github.com/llvm-beanz)
* Status: **Design In Progress**


## Introduction

HLSL's initializer lists assume a member-by-member flattened initialization
sequence. It is significantly different in behavior from C/C++ initializer
lists, but in a way that may not be apparent to users that they are depending on
the divergent behavior. This proposal suggests an approach to implementing
HLSL's initializer lists with a forward-looking perspective.

## Motivation

As an example, the initializer lists in the code below are all valid in HLSL today:

```hlsl
struct A {
  int a;
  double b;
};
struct B {
  A a[2];
  int c;
};
B b = {{1, 1.2}, {2, 2.2}, 3};   // Array elements specified as members
B b2 = {1, 2, 3, 4, 5};          // each field initialized separately
B b3 = {{1, {2, 3}}, {4, 5}};    // Completely random grouping of arguments
int4 i4 = {1,2,3,4};             // valid int4 in C-syntax
B b4 = {i4, 5};                  // int4 implicitly expanded to 4 arguments
```

In HLSL, initializer arguments are scalarized, and a member-by-member
initialization is performed in depth-first order from the initializer list to
the destination type. All scalarized fields in a destination type must map to a
scalarized field from an initializer argument, and the argument must be
convertible to the field type. It is an error if the source or destination type
have a different number of scalarized components when fully flattened.


In C++, initializer lists must represent the structure of the object they are
initializing, and each initializer in the list must be convertible to the
corresponding argument, however not all fields must be initialized. If the
initializer has less arguments than the target has fields, the remaining fields
are zero initialized. It is an error if an initializer list has too many
arguments, if an initializer has arguments that cannot be converted to the
destination type, or if an initializer list has incorrect nested braces.


The following examples which are valid in C++ are not valid in HLSL:

```c++
struct A {
  int a;
  double b;
};
struct B {
  A a[2];
  int c;
};
B b = {};
A a = {0};
B b2 = {{{0}}, 0};
B b3 = {{0}, 0};
```

Given the differences in the language described above it is likely too
significant of a change to make Clang follow C/C++ behavior without a transition
period. Since Clang and DXC will have different underlying representations for
resources and other built-in types, it is likely extremely difficult to make DXC
and Clang match on a new behavior. It will also be difficult to provide
migration tooling in DXC. For these reasons it is proposed to solve this problem
in Clang.

## Proposed solution

This solution is based on an assumption that we will adopt
[Proposal 0005 - Strict Initializer Lists](https://github.com/microsoft/hlsl-specs/blob/main/proposals/0005-strict-initializer-lists.md)
for HLSL 202y. The strict initializer lists proposal is motivated by a closer
alignment with C++, better error handling, and resolving incompatibilities with
variadic template initializer lists.

To facilitate implementing C++ initializer list behavior while also providing
compatibility with existing HLSL, this proposal suggests that Clang parse HLSL
initialization syntax into valid C++ initializer list ASTs.

This would mean that given an example like:

```hlsl
struct A {
  int a;
  double b;
};
struct B {
  A a[2];
  int c;
};
B b3 = {{1, {2, 3}}, {4, 5}};    // Completely random grouping of arguments
```

The initializer list for `b3` would be parsed into an AST something like:

```
InitListExpr
  InitListExpr
    InitListExpr
      IntegerConstant 1
      ImplicitCastExpr int->double
        IntegerConstant 2
    InitListExpr
      IntegerConstant 3
        ImplicitCastExpr int->double
          IntegerConstant 4
  IntegerConstant - 5
```

This AST structure allows the HLSL initializers to be implemented without any
need to change code generation. In an alternate example the AST can contain
member accesses with type checking of each conversion as well. Take the
following code and proposed AST:

```hlsl
float4 F = 1.0.xxxx;
struct A {
  int A, B;
  half C, D;
};

A a = {F};
```

```
InitListExpr
  ImplicitCastExpr float->int
    ExtVectorElementExpr .x
      DeclRefExpr F
  ImplicitCastExpr float->int
    ExtVectorElementExpr .y
      DeclRefExpr F
  ImplicitCastExpr float->half
    ExtVectorElementExpr .z
      DeclRefExpr F
  ImplicitCastExpr float->half
    ExtVectorElementExpr .w
      DeclRefExpr F
```

This full AST representation captures each element access and each type
conversion, which enables complete and accurate diagnostics which DXC cannot
provide today.

Further, this AST representation provides a full syntax tree that can be printed
out to a valid C++ initializer with the same behavior. The examples above would
be rewritten as:

```hlsl
B b3 = {{{1, 2}, {3, 4}}, 5};
A a = {F.x, F.y, F.z, F.w};
```

Because the AST would represent a valid C++ structure, we can make a refactoring
easily by just running the statement printer. 

<!-- {% endraw %} -->
