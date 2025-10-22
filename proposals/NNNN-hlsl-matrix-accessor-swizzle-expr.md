---
title: NNNN - HLSL Matrix Swizzle Expression
params:
  authors:
  + farzonl: Farzon Lotfi
  status: Design In Progress
---

## Introduction

The MatrixSwizzleExpr node is needed to extend Clang’s AST to accurately
represent matrix element “swizzling” syntax used in HLSL
(e.g., M._m00_m01, M._m10_m01 = 1.xx). Existing AST constructs such as
MatrixSubscriptExpr or ExtVectorElementExpr cannot fully capture this behavior
because they would not exactly match source spelling and per-component locations
and would not have correct l-value semantics and duplication rules.

## Requirements for a MatrixSwizzleExpr AST Node

To represent access like `M._m00_m01_m10` that can produce a vector of the
matrix element type.

For l-value cases:
* The base is an l-value and modifiable.
* The swizzle has no duplicate element references (same (row, col) repeated)
  on assignment.
  + example: this is not ok `M._m00_m00 = 1.xx;`

For r-value cases:
* Rvalues are allowed even with duplicates (like vector swizzles).
  + example: this is ok `float2 V = M._m00_m00;`

The AST Node must:
* Preserve exact spelling (token sequence after the dot) and per-component
  source locations for faithful printing and rewriting.
  + That means we store source location start and stop for each matrix element
    accessor in the swizzle.

* Be able to represent a matrix swizzle sequence between one to four elements.

## Implementation

### AST Implementation

We need a way to represent each element:

```cpp
struct Component {
    unsigned Row, Col;
    SourceLocation TokBegin, TokEnd;
  };
```

We will create a new expression that has a means of knowing if duplicates are in
the swizzle sequence. It should know the base matrix sequence, and a list to
keep track of components. It should be able to keep track of source location
from the dot to the last component in the sequence. It should know if we are
in a zero or one indexed sequence so as not to mix the two.

```cpp
class MatrixSwizzleExpr final : public Expr {
  private:
    Stmt *Base;                                 // matrix-typed expression
    llvm::SmallVector<Component, 4> Comps;      // selected (r,c) list
    SourceLocation DotLoc, UnderLoc;            // '.' and first '_' (after dot)
    StringRef FullSuffixSpelling;               // e.g. "_m00_m01" (owned by ASTContext)
    bool FromIdentifierToken : 1;               // was lexed as one ident (i.e., one index)
    bool HasDuplicates      : 1;
};
```

There should be a small parser to populate the Comps SmallVector.

### Codegen Implementation

After we add this new AST component, we need a special emitter similar to
`EmitExtVectorElementExpr` .

A new emitter `EmitMatrixSwizzleExpr` will be added. The codegen will breakdown
into two cases: R-Value and L-Value cases that will breakdown into either an
`EmitLoadOfScalar` or an `EmitExtVectorElementExpr` case.

R-value path:
* Emit Base to an address/aggregate per matrix lowering.
* For each (r, c), compute the element address and `EmitLoadOfScalar`.
* If N==1 and scalar policy we are done, just return that scalar.
* Else construct a VectorExt<N, T> via InsertElement.

L-value path:
* Only when `VK_LValue`. Represent as a pseudo-lvalue that, on store, scatters
  into the computed element addresses.
* Implement similar to `ExtVectorElementExpr` l-value: materialize an
  addressable proxy that on EmitStoreThroughLValue performs per-element stores.

### AST serialization implementation

Other than codegen, we also need to support AST serialization.
The files we need to modify are `ASTReaderStmt.cpp` and `ASTWriterStmt.cpp` .

This is where things like `FullSuffixSpelling` will be important.
The implementation should make sure we can encode the base stmt of the matrix, 
that it can capture all the rows and columns of the components in the swizzle.
We also need to consider if no duplicates and no index type mixing should be
enforced as part of serialization/deserialization.

### Miscellaneous

There might be some work that needs to be done to support clang tooling.
Investigation into ASTImporter or TreeTransform tools should be done.
