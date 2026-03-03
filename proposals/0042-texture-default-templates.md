---
title: "[0042] - Texture Default Templates"
params:
  authors:
    - s-perron: Steven Perron
  status: Under Consideration
  sponsors:
---

- PRs: [#184207](https://github.com/llvm/llvm-project/pull/184207)

## Introduction

This proposal describes the design and implementation for supporting default
template arguments and shorthand notation for HLSL texture types (e.g.,
`Texture2D`) in HLSL. This allows these types to be used without template
arguments or with an empty template list (e.g., `Texture2D` or `Texture2D<>`),
defaulting to an element type of `float4`, matching the behavior of the DirectX
Shader Compiler (DXC) in HLSL202x.

## Motivation

In HLSL, texture types are frequently used with a default element type of
`float4`. DXC allows developers to omit the template arguments entirely (e.g.,
`Texture2D`) or provide an empty template list (e.g., `Texture2D<>`).

Clang's current implementation of HLSL resources requires explicit template
arguments. Implementing this in Clang using standard C++ features like Class
Template Argument Deduction (CTAD) is problematic because:

1.  HLSL202x does not support user-defined CTAD, and enabling it globally would
    diverge from DXC's implementation.
2.  Resource handling in Clang (such as determining if a type is a resource via
    its handle and attributes) happens early in the compilation flow. Standard
    C++ template deduction occurs later, and many parts of the resource-specific
    semantic analysis expect a concrete type. Supporting "yet-to-be-deduced"
    resource types would require a significant and pervasive rewrite of the
    resource handling code in Clang.

The goal is to provide a surgical solution that matches DXC behavior while
maintaining the integrity of Clang's existing resource representation.

## Proposed solution

The proposed solution involves two complementary mechanisms:

1.  **Default Template Parameter**: Update the class template declarations for
    HLSL texture types in the HLSL External Sema Source to include a default
    template argument of `float4` (represented as `vector<float, 4>`). This
    natively enables the `Texture2D<>` syntax in C++.

2.  **Shorthand Notation Support**: Introduce a special case in Clang's semantic
    analysis to intercept the use of a template name without any template
    arguments. When an identifier for an HLSL texture type is encountered in a
    context where a type is expected, and it is identified as an HLSL resource
    template, Clang will automatically instantiate the template with its default
    parameters.

## Detailed design

### BuiltinTypeDeclBuilder Enhancements

The `BuiltinTypeDeclBuilder` utility, used to generate HLSL resource types in
the External Sema Source, is updated to support default template parameters:

```cpp
BuiltinTypeDeclBuilder &
BuiltinTypeDeclBuilder::addSimpleTemplateParams(ArrayRef<StringRef> Names,
                                                ArrayRef<QualType> DefaultValues,
                                                ConceptDecl *CD);
```

This allows the registration code to specify `float4` as the default for the
`element_type` parameter of texture types.

### HLSLExternalSemaSource Integration

The initialization of texture types in `HLSLExternalSemaSource.cpp` is modified
to provide the default type. For `Texture2D`, it would look like:

```cpp
QualType Float4Ty = AST.getExtVectorType(AST.FloatTy, 4);
Decl = BuiltinTypeDeclBuilder(*SemaPtr, HLSLNamespace, "Texture2D")
           .addSimpleTemplateParams({"element_type"}, {Float4Ty},
                                    TypedBufferConcept)
           .finalizeForwardDeclaration();
```

### Semantic Analysis (Sema)

A new method, `SemaHLSL::ActOnTemplateShorthand`, is added to handle the
conversion of a template name to a concrete type:

1.  **Intercepting Template Names**: In `Sema::getTypeName`, when an identifier is
    successfully resolved but identifies a template, and the language is HLSL,
    `ActOnTemplateShorthand` is called before falling back to Class Template
    Argument Deduction (CTAD) or erroring.
2.  **Validation**: The function verifies that the template belongs to the
    `hlsl` namespace and has default arguments for all its template parameters.
3.  **Synthesis**: It iterates through the template parameters and retrieves the
    default arguments from the declaration to construct a complete
    `TemplateArgumentListInfo`. It then calls `Sema::CheckTemplateIdType` to
    produce a fully qualified `QualType`.

### Testing Strategy

1.  **AST Verification**: Use `-ast-dump` to ensure that `Texture2D`,
    `Texture2D<>`, and `Texture2D<float4>` (and other texture types) all result
    in a `ClassTemplateSpecializationDecl` with `float4` as the template
    argument when shorthand or empty templates are used.
2.  **CodeGen Verification**: Verify that variables declared with shorthand
    notation correctly lower to LLVM IR with the expected target extension types
    (e.g., `target("dx.Texture", <4 x float>, ...)`).
3.  **Binding and Semantics**: Ensure that the shorthand types work correctly
    with HLSL-specific features like `register` bindings and member function
    calls (e.g., `Sample`). This tests that the texture can be identified as a
    resource early in the compilation.

## Alternatives considered

### Class Template Argument Deduction (CTAD)

As mentioned in the motivation, CTAD was considered but rejected because it is
not officially supported in HLSL202x and would require significant architectural
changes to handle undeduced resources in early Sema passes.

### Type Aliases

We considered using `typedef Texture2D<float4> Texture2D;` or declaring a
non-template type alongside the template type. This was quickly rejected because
it would break the usual C++ lookup. Creating these types of special cases is
not a good solution.
