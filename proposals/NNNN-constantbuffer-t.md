---
title: "[NNNN] - HLSL ConstantBuffer<T> Implementation"
params:
  authors: Steven Perron
    - github_username: s-perron
  status: Under Consideration
  sponsors: Steven Perron
    - github_username: s-perron
---

## Introduction

This proposal details the implementation of the `ConstantBuffer<T>` resource
type in Clang and LLVM for HLSL. Unlike the legacy `cbuffer` keyword, where each
member of the `cbuffer` becomes its own global variable, `ConstantBuffer<T>`
behaves as a standard type, supporting instantiation, arrays, function
parameters, and assignments. The `ConstantBuffer<T>` type acts more like other
resource type than it does a `cbuffer`. The unique aspect of the
`ConstantBuffer<T>` type is that it can be used as a drop in replacement for
`T`, as if ConstantBuffer<T> inherited from `T`. However, it is not really
inheritance.

## Motivation

HLSL developers require `ConstantBuffer<T>` as it is part of the language
standard, and it is used.

## Proposed solution

We propose implementing `ConstantBuffer<T>` as a built-in template class that
provides an implicit conversion to `T &`. To ensure a seamless developer
experience, `Sema` will be modified to automatically inject this conversion when
accessing members of a `ConstantBuffer`.

### Frontend (Clang AST/Sema)

1.  **Built-in Template:** Define `ConstantBuffer<T>` in
    `HLSLExternalSemaSource.cpp` as a template class containing a single
    `__hlsl_resource_t` member (the handle). The handle's contained type is
    exactly `T`.
2.  **Implicit Conversion Operator:** Define an implicit conversion operator
    `operator const T &() const` within the `ConstantBuffer<T>` template.
3.  **Sema Member Lookup Interception:** Modify `Sema::LookupMemberExpr` (in
    `SemaExprMember.cpp`) to detect member accesses on `ConstantBuffer<T>`. If
    detected, Sema will inject a call to the implicit conversion operator,
    effectively transforming `cb.field` into `((const T &)cb).field`.
4.  **Sema Constraints:** Enforce that `T` must be a user-defined struct or
    class, and reject primitive types, vectors, arrays, or matrices as `T`.
5.  **Copy Semantics:** Define a custom copy constructor and copy assignment
    operator that strictly copies the `__hlsl_resource_t` handle. This ensures
    the `ConstantBuffer` remains a lightweight reference to the underlying
    resource.

### CodeGen (Clang)

1.  **Handle Types:** Emit instances of `ConstantBuffer<T>` using the
    `target("dx.CBuffer", T)` extension type.
2.  **Conversion Operator Implementation:** The conversion operator is
    implemented using a new HLSL-specific builtin
    `__builtin_hlsl_resource_getpointer`.
3.  **Intrinsic Redirection:** In CodeGen, this builtin lowers to a new overload
    of the `llvm.dx.resource.getpointer` intrinsic. Unlike the version used for
    buffers, this overload does not take an offset index, as `ConstantBuffer`
    always represents a single instance of `T` at the start of the buffer.
    - `ptr addrspace(2) @llvm.dx.resource.getpointer(target("dx.CBuffer", T) %handle)`
4.  **Pointer Address Space:** The resulting pointer targets the appropriate
    constant/uniform address space (`addrspace(2)` for DXIL, `addrspace(12)` for
    SPIR-V). Standard CodeGen then applies `getelementptr` for field access.

### Backend (LLVM)

**New Intrinsic Overload:** This implementation requires a new overload for the
resource pointer intrinsics:

- `llvm.dx.resource.getpointer`
- `llvm.spv.resource.getpointer`

Previously, these intrinsics required an index parameter (used for
arrays/buffers). The new overload takes _only_ the resource handle, representing
an access to the base of the resource, which aligns perfectly with
`ConstantBuffer` semantics.

The LLVM backend will translate this new `getpointer` overload and the
subsequent `getelementptr` and `load` operations into the appropriate
`dx.op.cbufferLoadLegacy` or `dx.op.cbufferLoad` operations in DirectX, or the
equivalent `OpAccessChain` and `OpLoad` operations in SPIR-V.

## Detailed design

### Built-in Class Definition

The `ConstantBuffer<T>` type is defined in the compiler conceptually as the
following C++ template class:

```cpp
template <typename T>
class ConstantBuffer {
  // Underlying handle with resource class CBuffer and contained type T
  __hlsl_resource_t [[hlsl::resource_class(CBuffer)]] [[hlsl::contained_type(T)]] __handle;

public:
  // Implicit conversion to const reference of type T
  operator const T&() const {
    return (const T&)__builtin_hlsl_resource_getpointer(__handle);
  }

  // Copy operations copy the handle, not the underlying data
  ConstantBuffer(const ConstantBuffer& other) {
    __handle = other.__handle;
  }

  ConstantBuffer& operator=(const ConstantBuffer& other) {
    __handle = other.__handle;
    return *this;
  }
};
```

### Usage Examples and AST Generation

#### 1. Member Access

When an HLSL developer accesses a member directly from the `ConstantBuffer`,
`Sema` intercepts the member lookup and injects a call to the implicit
conversion operator.

```hlsl
struct S { float a; float b; };
ConstantBuffer<S> cb;
float main() {
  return cb.a;
}
```

**AST Structure:**

```text
`-MemberExpr 'float' lvalue .a
  `-CXXMemberCallExpr 'S' lvalue
    `-MemberExpr '<bound member function type>' .operator S &
      `-ImplicitCastExpr 'const hlsl::ConstantBuffer<S>' lvalue <NoOp>
        `-DeclRefExpr 'cb'
```

#### 2. Local Assignment

Assigning a `ConstantBuffer<T>` to a local variable of type `T` triggers the
implicit conversion operator, followed by `T`'s standard copy constructor.

```hlsl
S local = cb;
```

**AST Structure:**

```text
`-CXXConstructExpr 'S' 'void (const S &)'
  `-ImplicitCastExpr 'const S' lvalue <NoOp>
    `-ImplicitCastExpr 'S' lvalue <UserDefinedConversion>
      `-CXXMemberCallExpr 'S' lvalue
        `-MemberExpr '<bound member function type>' .operator S &
          `-ImplicitCastExpr 'const hlsl::ConstantBuffer<S>' lvalue <NoOp>
            `-DeclRefExpr 'cb'
```

#### 3. Function Parameters

Passing a `ConstantBuffer<T>` to a function expecting `T` invokes the implicit
conversion. Passing it to a function expecting `ConstantBuffer<T>` invokes the
handle-copying constructor.

```hlsl
void takes_s(S s) {}
void takes_cb(ConstantBuffer<S> c) {}

void test() {
  takes_s(cb);  // Calls operator S&() and copies data into argument
  takes_cb(cb); // Calls ConstantBuffer(const ConstantBuffer&) and copies handle
}
```

#### 4. Array Indexing

For arrays of `ConstantBuffer`, the subscript operator first resolves the
handle, and then the implicit conversion occurs on the indexed element.

```hlsl
ConstantBuffer<S> cb_arr[2];
float f = cb_arr[1].a;
```

#### 5. Template Support

`ConstantBuffer<T>` can be passed to templates. Because `Sema` intercepts member
access on the `ConstantBuffer` type itself, template functions that perform
member access on deduced `ConstantBuffer` types will work correctly.

```hlsl
template<typename Tm>
void foo(Tm t) {
  float f = t.a; // Works even if Tm is ConstantBuffer<S>
}

void test() {
  foo(cb); // Tm is deduced as ConstantBuffer<S>
}
```

In the primary template `foo`, the expression `t.a` is represented as a
`CXXDependentScopeMemberExpr` because the type of `t` is dependent:

```text
`-CXXDependentScopeMemberExpr '<dependent type>' lvalue .a
  `-DeclRefExpr 'Tm' lvalue ParmVar 't' 'Tm'
```

When `foo` is instantiated as `foo<ConstantBuffer<S>>`, Clang's template
instantiation mechanism rebuilds the member expression. Since the type of `t` is
now known to be `ConstantBuffer<S>`, the standard member lookup logic in
`Sema::LookupMemberExpr` is triggered. Our interception logic then identifies
`ConstantBuffer<S>` and injects the call to the implicit conversion operator
`operator S&()`, resulting in the same AST structure as non-templated member
access:

```text
`-MemberExpr 'float' lvalue .a
  `-CXXMemberCallExpr 'S' lvalue
    `-MemberExpr '<bound member function type>' .operator S &
      `-ImplicitCastExpr 'const hlsl::ConstantBuffer<S>' lvalue <NoOp>
        `-DeclRefExpr 't' 'hlsl::ConstantBuffer<S>'
```

This ensures that `ConstantBuffer<T>` remains a "drop-in" replacement for `T`
even in generic code, as the transformation happens seamlessly during template
instantiation.

### CodeGen and LLVM IR

When Clang emits LLVM IR for the `operator T&()` conversion, it utilizes the
`llvm.dx.resource.getpointer` (or `llvm.spv.resource.getpointer`) intrinsic to
retrieve an address space qualified pointer.

#### DXIL Example

For the member access `cb.a`, the target pointer is in `addrspace(2)` (the DXIL
constant address space).

```llvm
; The handle type
%"class.hlsl::ConstantBuffer" = type { target("dx.CBuffer", %struct.S) }

; 1. The implicit conversion resolves to the getpointer intrinsic
%handle = load target("dx.CBuffer", %struct.S), ptr %cb, align 4
%base_ptr = call ptr addrspace(2) @llvm.dx.resource.getpointer.p2.tdx.CBuffer_s_Sst(target("dx.CBuffer", %struct.S) %handle)

; 2. The MemberExpr applies a GEP
%gep = getelementptr inbounds %struct.S, ptr addrspace(2) %base_ptr, i32 0, i32 0

; 3. Finally, the value is loaded
%val = load float, ptr addrspace(2) %gep, align 4
```

#### SPIR-V Example

For SPIR-V (Vulkan), the handle is a `spirv.VulkanBuffer`, and the uniform
pointer is in `addrspace(12)`.

```llvm
; The handle type
%"class.hlsl::ConstantBuffer" = type { target("spirv.VulkanBuffer", %struct.S, 2, 0) }

; 1. Pointer acquisition
%handle = load target("spirv.VulkanBuffer", %struct.S, 2, 0), ptr %cb, align 8
%base_ptr = call ptr addrspace(12) @llvm.spv.resource.getpointer.p12.tspirv.VulkanBuffer_s_Sst(target("spirv.VulkanBuffer", %struct.S, 2, 0) %handle)

; 2. GEP and load
%gep = getelementptr inbounds %struct.S, ptr addrspace(12) %base_ptr, i32 0, i32 0
%val = load float, ptr addrspace(12) %gep, align 4
```

## Alternatives considered

### Reusing the Legacy `cbuffer` Model

In the legacy model, members of a `cbuffer` are emitted as individual global
variables in the `hlsl_constant` address space. These globals are then linked to
a resource handle via metadata (`!hlsl.cbs`).

While this works for flat, global `cbuffer` declarations, it is fundamentally
incompatible with `ConstantBuffer<T>` for several reasons:

- **Encapsulation:** In `ConstantBuffer<T>`, members are scoped within the
  template instance. Treating them as global variables would violate this
  scoping and require complex name mangling and metadata schemes.
- **Dynamic Handles:** Metadata-based linking is static. In modern HLSL,
  `ConstantBuffer<T>` can be indexed (arrays) or passed as parameters, meaning
  the handle is often dynamic and cannot be linked to a global variable at
  compile time via static metadata.
- **Complexity:** Reusing the legacy model for a modern resource type would
  require significant "backward" modifications to Clang's resource handling,
  whereas the proposed pointer-based model aligns with how other modern
  resources (like `RWBuffer`) are implemented.

### `ConstantBuffer<T>` inheriting from `T`

A significant alternative considered was to have `ConstantBuffer<T>` inherit
from `T`. This would allow standard C++ member lookup and implicit conversions
(via slicing) to work "out of the box" in Sema.

However, this approach was rejected for several technical and architectural
reasons:

- **AST Inaccuracy:** The AST would imply that a `ConstantBuffer` _is_ a `T`,
  which is not physically true. `ConstantBuffer` is a small wrapper around a
  resource handle; it does not contain the data of `T` inline.
- **Memory Layout:** Inheritance would force the AST's
  `sizeof(ConstantBuffer<T>)` to be at least `sizeof(T)`. This bloat is
  misleading and could lead to bugs in parts of the compiler that rely on
  accurate record sizes (e.g., alignment, padding, or future features).
- **Special Case Overload:** To achieve correct CodeGen, we would still need to
  intercept `DerivedToBase` casts to prevent the compiler from attempting to
  access the (non-existent) base class data via standard pointer arithmetic.
  This effectively trades one type of Sema/CodeGen hack for another, more
  confusing one.
- **Maintainability:** Creating a "fake" inheritance relationship introduces a
  fundamental lie into the AST that every future compiler developer would have
  to be aware of and handle as a special case. The proposed implicit conversion
  model is more honest and follows standard C++ patterns for wrapper types.

## Open questions

1.  **Layout Consistency:** What needs to be done to ensure that the struct `T`
    used in `ConstantBuffer<T>` is laid out correctly? It must match the layout
    rules of the legacy `cbuffer`.
2.  **Address Space Conversions:** How will different address spaces affect the
    implicit conversions? Will we need multiple conversion operators to handle
    different target address spaces or cv-qualifiers?

## Acknowledgments

Special thanks to the HLSL working group for examining the limitations of the
legacy cbuffer design and refining the inheritance and pointer-based codegen
model.
