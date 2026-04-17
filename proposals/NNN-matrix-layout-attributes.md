
---
title: "[NNNN] - Matrix Layout Attributes"
params:
  authors:
    - farzonl: Farzon Lotfi
  status: Under Consideration
  sponsors:
---

## Motivation
HLSL allows per-declaration matrix layout overrides via the row_major and column_major keywords. So far in clang the matrix layout is only controlable globally via the `-fmatrix-memory-layout` command-line flag (`LangOptions::DefaultMatrixMemoryLayout`). We need to add the parsing and semantic analysis, and codegen infrastructure needed to support per-declaration layout, matching DXC behavior.

## The plan
### 1. Keyword Registration (TokenKinds.def)
We need to do the same thing we did for `KEYWORD(cbuffer, KEYHLSL)`.
Add `row_major` and `column_major` as `KEYWORD(..., KEYHLSL)` entries.
This will limit the  keywords to HLSL while allowing them to remain identifers in C/C++ and other langugage modes.

### 2. Attribute Definition (Attr.td)
A new `HLSLMatrixLayout` inheritable attribute is needed with:
- It must cover both keywords.
- The Spelling should be a CustomKeyword  because the token kinds are explicitly defined in TokenKinds.def.
- We should still add LangOpts: [HLSL] to  restricts the attribute to HLSL mode.

### 3. Parsing (ParseDecl.cpp)
Now that we have a `tok::kw_row_major` and `tok::kw_column_major` we need to consume the token the same way we consume `tok::kw_groupshared`. Ie we need to call `ParseHLSLQualifiers()`.
We also need to modify `isTypeSpecifierQualifier` because the matrix layout attributes are a type-specifier.

### 4. Semantic Analysis (SemaHLSL.cpp, SemaDeclAttr.cpp)
A new `SemaHLSL::handleMatrixLayoutAttr` handler is needed so that    `ProcessDeclAttribute` can handle the `ParsedAttr::AT_HLSLMatrixLayout` case.
The handler should performs three validations:

- Type check: The declaration's type must be a `ConstantMatrixType`. 
- Conflict check: If the declaration already has an  `HLSLMatrixLayoutAttr`   with a different spelling (e.g., `row_major column_major float3x3`), an   error is emitted.
- Duplicate check: If the declaration already has an `HLSLMatrixLayoutAttr`   with the same spelling (e.g.,   `row_major row_major float3x3`), a warning   is emitted.

### 5. Diagnostics (DiagnosticSemaKinds.td)
We need some new diagnostics:
- Limit the attribute to only matrix types"
- Make sure we can't apply conflicting attributes (eg. row and column major)

### 6. Tests (Parser and Sema)
Tests we need:
- Sema Errors on scalars, vectors, arrays, structs. Conflict and duplicate diagnostics.
- AST dump with correct spelling for variables, fields, and typedefs.
- Verifies row_major/column_major are not keywords in C++ mode.

### 7. Update All global layout check to check attribute first.
 The curent behavior checks `getLangOpts().getDefaultMatrixMemoryLayout()`. This needs to be updated to first check for an `HLSLMatrixLayoutAttr` on the relevant declaration before falling back to the global default. A helper function like `isMatrixRowMajor(const Expr *E)` would centralize this logic.

#### Codegen Files (where layout affects IR)

Below are the areas in Codgen that needed to be updated.

| File:Line                | Purpose                         |
|--------------------------|---------------------------------|
| [CGExpr.cpp:2339]        | Matrix element l-value access   |
| [CGExpr.cpp:2596]        | Matrix subscript store          |
| [CGExpr.cpp:2904]        | Matrix subscript load           |
| [CGExpr.cpp:5191]        | Matrix element member expr      |
| [CGExpr.cpp:7401]        | Matrix element store            |
| [CGExprScalar.cpp:2242]  | Matrix cast                     |
| [CGExprScalar.cpp:2269]  | Matrix truncation cast          |
| [CGExprScalar.cpp:2355]  | Matrix multiply                 |
| [CGExprScalar.cpp:2595]  | Matrix binary ops               |
| [CGExprScalar.cpp:3175]  | Matrix compound assign          |
| [CGExprConstant.cpp:2648]| Constant matrix init list       |
| [CGHLSLBuiltins.cpp:1185]| HLSL mul builtin                |
| [CGHLSLBuiltins.cpp:1238]| HLSL transpose builtin          |
| [CodeGenTypes.cpp:115]   | Matrix type → LLVM IR type      |

[CGExpr.cpp:2339]: https://github.com/llvm/llvm-project/blob/5f62bae5666c3cad5439587fa0f330b92467241a/clang/lib/CodeGen/CGExpr.cpp#L2339
[CGExpr.cpp:2596]: https://github.com/llvm/llvm-project/blob/5f62bae5666c3cad5439587fa0f330b92467241a/clang/lib/CodeGen/CGExpr.cpp#L2596
[CGExpr.cpp:2904]: https://github.com/llvm/llvm-project/blob/5f62bae5666c3cad5439587fa0f330b92467241a/clang/lib/CodeGen/CGExpr.cpp#L2904
[CGExpr.cpp:5191]: https://github.com/llvm/llvm-project/blob/5f62bae5666c3cad5439587fa0f330b92467241a/clang/lib/CodeGen/CGExpr.cpp#L5191
[CGExpr.cpp:7401]: https://github.com/llvm/llvm-project/blob/5f62bae5666c3cad5439587fa0f330b92467241a/clang/lib/CodeGen/CGExpr.cpp#L7401

[CGExprScalar.cpp:2242]: https://github.com/llvm/llvm-project/blob/5f62bae5666c3cad5439587fa0f330b92467241a/clang/lib/CodeGen/CGExprScalar.cpp#L2242
[CGExprScalar.cpp:2269]: https://github.com/llvm/llvm-project/blob/5f62bae5666c3cad5439587fa0f330b92467241a/clang/lib/CodeGen/CGExprScalar.cpp#L2269
[CGExprScalar.cpp:2355]: https://github.com/llvm/llvm-project/blob/5f62bae5666c3cad5439587fa0f330b92467241a/clang/lib/CodeGen/CGExprScalar.cpp#L2355
[CGExprScalar.cpp:2595]: https://github.com/llvm/llvm-project/blob/5f62bae5666c3cad5439587fa0f330b92467241a/clang/lib/CodeGen/CGExprScalar.cpp#L2595
[CGExprScalar.cpp:3175]: https://github.com/llvm/llvm-project/blob/5f62bae5666c3cad5439587fa0f330b92467241a/clang/lib/CodeGen/CGExprScalar.cpp#L3175

[CGExprConstant.cpp:2648]: https://github.com/llvm/llvm-project/blob/5f62bae5666c3cad5439587fa0f330b92467241a/clang/lib/CodeGen/CGExprConstant.cpp#L2648

[CGHLSLBuiltins.cpp:1185]: https://github.com/llvm/llvm-project/blob/5f62bae5666c3cad5439587fa0f330b92467241a/clang/lib/CodeGen/CGHLSLBuiltins.cpp#L1185
[CGHLSLBuiltins.cpp:1238]: https://github.com/llvm/llvm-project/blob/5f62bae5666c3cad5439587fa0f330b92467241a/clang/lib/CodeGen/CGHLSLBuiltins.cpp#L1238

[CodeGenTypes.cpp:115]: https://github.com/llvm/llvm-project/blob/5f62bae5666c3cad5439587fa0f330b92467241a/clang/lib/CodeGen/CodeGenTypes.cpp#L115


#### Sema Files (semantic checks)

Below are the areas in Sema that need to be updated.

| File:Line                   | Purpose                          |
|-----------------------------|----------------------------------|
| [SemaChecking.cpp:16978]    | Init list element order check    |
| [SemaChecking.cpp:17102]    | Init list element order check    |

[SemaChecking.cpp:16978]: https://github.com/llvm/llvm-project/blob/5f62bae5666c3cad5439587fa0f330b92467241a/clang/lib/Sema/SemaChecking.cpp#L16978
[SemaChecking.cpp:17102]: https://github.com/llvm/llvm-project/blob/5f62bae5666c3cad5439587fa0f330b92467241a/clang/lib/Sema/SemaChecking.cpp#L17102

### 8. Tests (Codgen and Init Order)
We need tests that match the stated purposes in the above two tables.
