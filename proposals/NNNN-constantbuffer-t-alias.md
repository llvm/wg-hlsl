---
title: "[NNNN] - HLSL ConstantBuffer<T> Type Alias Implementation"
params:
  authors: Steven Perron
    - github_username: s-perron
  status: Under Consideration
  sponsors: Steven Perron
    - github_username: s-perron
---

## Introduction

This proposal details an implementation of the `ConstantBuffer<T>` resource type
in Clang and LLVM for HLSL. In this design, `ConstantBuffer<T>` is defined as a
type alias to the `hlsl_constant` address space.

## Proposed solution

We propose implementing `ConstantBuffer<T>` as a template alias:

```cpp
template <typename T>
using ConstantBuffer = [[hlsl::address_space(hlsl_constant)]] T;
```

This design leverages the C++ type system to handle member access naturally.
However, since `ConstantBuffer<T>` represents a resource rather than a standard
value, several semantic and code generation adjustments are required to maintain
HLSL's resource behaviors.

### Frontend (Clang AST/Sema)

The main part of this design is that `ConstantBuffer<T>` is defined as a
`TypeAliasTemplateDecl` that maps to `[[hlsl::address_space(hlsl_constant)]] T`.
However, this does not solve all of the issues for `ConstantBuffer<T>`.

Problems to solve:

1. **Resource aliases:** The type `ConstantBuffer<T>` can appear in different
   contexts where it acts as a reference to an actual global resource.
   1. **Initialization:** Resource aliases do not require mandatory
      initialization.
   2. **Reassignment:** Resource aliases can change which resource they
      reference via assignment.
   3. **Scope:** Resource aliases may be local variables, global statics,
      parameters, or return values. They may appear standalone, in arrays, or
      within structs.
   4. See https://godbolt.org/z/Px5P79nKv for an example where it is used in
      many locations.
2. Handle creation and Initialization
   1. Handle is not explicit: In this design the handle is not explicit, so we
      cannot reuse the design for other resource types like StructureBuffer and
      Texture2D.
   2. HLSLBufferDecl: initialization of the ConstantBuffer will have to be
      expanded to handle arrays of resources.

Below we sketch out possible solutions to these problems with guesses at the
work required to make it work.

#### Resource aliases as references

To properly represent a resource alias, we will have to change the type to be
able to recognize the difference between the actual resource, and the resource
alias. The most natural way to do that is to turn it into a reference. This
could work well because the syntax to use the resource alias will be the same as
the resource itself. However, a resource alias does not work exactly like a
reference. There are two main differences. First, a resource alias does not
require initialization upon declaration. Second, assigning to a resource alias
updates the referent rather than performing a value-copy of the underlying
buffer data. In C++, references have to be initialized, and the data it
references cannot be changed. In this respect, resource aliases are more like a
pointer with the syntax of a reference.

To make this design work, we will have to:

1. In Sema, all declarations of a ConstantBuffer<T> will have to be assessed to
   know whether the variable is an alias or not.
   1. This will have to be done carefully to make sure it works with type
      deduction. For example, what should `auto B() { return G; }` return?
   2. There are many places we need to check for this change:
      1. `Sema::CheckVariableDeclaration`: This will allow us to rewrite
         variable declarations. We recommend doing this here instead of
         `SemaHLSL::ActOnVariableDeclarator` because the `ActOn*` hooks are
         bypassed during template instantiation, whereas
         `CheckVariableDeclaration` is called for both parsed and instantiated
         code. There is precedent for type mutations here. We could use
         SemaHLSL::ActOnVariableDeclarator, but it would have to call it from
         more places to properly handle templates.
      2. `Sema::CheckFunctionDeclaration`: This will allow us to rewrite
         function return types, including those instantiated from templates.
      3. `Sema::ActOnParamDeclarator` and `SemaType.cpp`: This will allow us to
         rewrite parameters (similar to how `inout` is handled). **Note**: It is
         currently unclear how to handle cases where the parameter type is a
         template parameter (e.g., `template<typename T> void f(T p)`) that is
         later instantiated as a `ConstantBuffer<T>`. We need to determine if
         these should also be implicitly converted to references during
         instantiation.
      4. Add hook in type deduction: Type deduction does not go through the
         functions above initially. We will need to interpret the type deduction
         and make it a reference if the `auto` is used in the correct context
         (e.g., leveraging `Sema::DeduceVariableDeclarationType` and
         `HLSL().deduceAddressSpace`).
      5. Templates: By using the `Check*` functions, we handle most
         instantiation issues, but we might need to add more code to do rewrites
         in specific template instantiation paths if attributes are dropped.
      6. Note that special care will have to be taken when handling structs. The
         actual type of a struct containing a `ConstantBuffer<T>` depends on the
         context in which the struct is used: https://godbolt.org/z/evq96evfK.
         All of these locations will have to traverse members of aggregate types
         to make sure the members are correctly rewritten.
2. All places in Sema that do assignments of one object to another will have to
   be updated. Assignments to the resource alias change the referent, but a
   typical assignment to a reference copies all of the data. To allow for this
   distinction, we will add a new attribute `hlsl::reassignable` to the resource
   aliases. Places to change:
   1. Handling of the assignment operator.
      1. We will require that the RHS be a global variable in the hlsl_constant
         address space or another resource alias with the same type.
      2. We will want to avoid the cast to RValue for the RHS so that codegen
         knows we are modifying the reference and not the data. **Note**: this
         could be handled other ways, but we need to do something, and I don't
         like ignoring the cast to RValue in codegen.
      3. The HLSL struct copying that is being implemented will have to handle
         this case.
      4. I don't know if there are other places we will need to special case.
   2. Allow for uninitialized references.
      1. The code that issues an error when there is no initializer for a
         reference will require a special case.
      2. We will need to make sure that no other code assumes references have
         initializers. It will have to be updated to handle our case. (Unknown).

#### Handle Initialization

The current design for `cbuffers` is to create an HLSLBufferDecl to represent
the buffer. The current design is not expressive enough to allow for an array of
resources. We would have to make some changes for it to work. The specific
design still needs to be determined, but it will require changes in Sema, clang
codegen, and the CBuffer access passes in the backend. It could be done, but is
not intuitive.
