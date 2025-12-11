---
title: 0036 - HLSL Matrix Element Expression
params:
  authors:
    farzonl: Farzon Lotfi
status: Accepted
---

## Introduction

HLSL supports matrix “element accessor” syntax that can name individual elements
or swizzles of elements, for example:

- `M._m00` (zero-based, one element)
- `M._11` (one-based, one element)
- `M._m00_m11` (zero-based swizzle)
- `M._11_22_33` (one-based swizzle)

To represent these in Clang’s AST we introduce `MatrixElementExpr`, an
expression node that is structurally similar to `ExtVectorElementExpr`, but
specialized for matrices.

`MatrixElementExpr`:

- Represents both scalar matrix element access and matrix swizzles.
- Preserves the accessor spelling (e.g. `_m00_m11`) as a single identifier.
- Implements the HLSL rules for 0-based (`_mRC`) vs 1-based (`_RC`) accessors.
- Enforces l-value semantics (no duplicate components on assignment) analogous
  to vector swizzles.

Unlike the earlier proposal for a dedicated `MatrixSwizzleExpr` with an
explicit per-component list and per-component source locations, the final
design:

- Reuses the existing `ExtVectorElementExpr` machinery via a shared base class.
  - Per [Aaron Ballman's Feedback](https://discourse.llvm.org/t/rfc-extend-extvectorelementexpr-for-hlsl-matrix-accessors/88802/4)
  - ExtVectorElementExpr is migrated to use this base.
  - MatrixElementExpr is introduced as a sibling.
- Keeps the AST node compact, storing only the base expression, the accessor
  identifier, and the accessor source location.
- Computes row/column indices and duplicate information on demand.

## Requirements for a MatrixElementExpr AST Node

We want to represent access such as `M._m00_m01_m10` that can produce a vector
of the matrix element type, as well as single-element cases like `M._m00`.

### General

- The node must be usable for:
  - Scalar element access: `float r = A._m00;`
  - Swizzle access for 1 to 4 elements: `float3 v = A._11_22_33;`
- The accessor must follow the HLSL matrix rules:
  - Zero-based form: `_mRC` where `R` and `C` are decimal digits.
  - One-based form: `_RC` where `R` and `C` are decimal digits.
  - A swizzle is a `_`-separated sequence of those forms:
    - `_m00_m11`, `_11_22_33`, etc.
- Swizzle length must be between 1 and 4 (inclusive). Invalid lengths should
  be rejected during semantic analysis.

### L-value vs R-value semantics

For l-value (assignment) cases:

- The base must be a modifiable l-value matrix.
- The swizzle must not contain duplicate element references (same `(row, col)`
  pair repeated) when used as a store destination.
  - Example (not allowed): `A._m00_m00 = float2(1, 2);`
- Assignments with duplicate components should be rejected with an error akin
  to “matrix is not assignable (contains duplicate components)”.

For r-value cases:

- Reads are allowed even with duplicate components, analogous to vector
  swizzles.
  - Example (allowed): `float2 v = A._m00_m00;`
- The number of components in the accessor determines the result type:
  - 1 component → scalar element type.
  - N components (2–4) → `vector<N, element-type>`.

### Bounds and accessor validation

Sema must validate that:

- The accessor uses one of the supported forms (`_mRC` or `_RC`).
- The indices are within bounds for the matrix type:
  - For zero-based accessors, `R` and `C` must be in `[0, rows-1]` and
    `[0, cols-1]`.
  - For one-based accessors, `R` and `C` must be in `[1, rows]` and
    `[1, cols]`.
- Clear diagnostics are produced for:
  - Accessors that are lexically malformed (bad characters, wrong length,
    wrong prefix, mixed forms in a single accessor string).
  - Accessors that are syntactically correct but out-of-bounds for the
    given matrix type.
  - Swizzle lengths that are not in `[1, 4]`.

## Implementation

### AST Implementation

We introduce a small CRTP base for element-like access expressions that are
spelled via a single identifier and applied to a base expression:

```cpp
template <typename Derived>
class ElementAccessExprBase : public Expr {
  Stmt *Base;
  IdentifierInfo *Accessor;
  SourceLocation AccessorLoc;

protected:
  ElementAccessExprBase(StmtClass SC, QualType Ty, ExprValueKind VK,
                        Expr *Base, IdentifierInfo &Accessor,
                        SourceLocation Loc, ExprObjectKind OK)
      : Expr(SC, Ty, VK, OK),
        Base(Base),
        Accessor(&Accessor),
        AccessorLoc(Loc) {
    setDependence(computeDependence(static_cast<Derived *>(this)));
  }

  explicit ElementAccessExprBase(StmtClass SC, EmptyShell Empty)
      : Expr(SC, Empty) {}

public:
  const Expr *getBase() const { return cast<Expr>(Base); }
  Expr *getBase() { return cast<Expr>(Base); }
  void setBase(Expr *E) { Base = E; }

  IdentifierInfo *getAccessor() const { return Accessor; }
  void setAccessor(IdentifierInfo *II) { Accessor = II; }

  SourceLocation getAccessorLoc() const { return AccessorLoc; }
  void setAccessorLoc(SourceLocation L) { AccessorLoc = L; }

  SourceLocation getBeginLoc() const { return getBase()->getBeginLoc(); }
  SourceLocation getEndLoc() const { return AccessorLoc; }

  /// Helpers implemented by the derived class:
  ///
  ///   - unsigned getNumElements() const;
  ///   - bool containsDuplicateElements() const;
  ///   - void getEncodedElementAccess(SmallVectorImpl<uint32_t> &Elts) const;
};
```