---
title: "[0027] - SPIR-V Specialization Constants"
params:
  status: Design In Progress
  authors:
    - s-perron: Steven Perron
---

## Introduction

SPIR-V has a feature called
[Specialization Constants](https://registry.khronos.org/SPIR-V/specs/unified1/SPIRV.html#_specialization_2)
that allows shader code to have constants that are set by the driver. This
feature is exposed in HLSL via the `vk::constant_id` attribute.

## Motivations

This feature is commonly used in Vulkan to avoid creating multiple versions of
the same shader for each value of the constant. It was implemented in DXC, so we
want to match that behavior.

## Proposed solution

The `vk::constant_id` attribute applies to a global constant scalar variable:

```
[[vk::constant_id(0)]] const float my_constant = 1.0f;
```

This indicates that the value of `my_constant` can be overridden by the driver
by providing a value for specialization constant ID `0`. If no value is provided
by the driver for this ID, then `my_constant` will take its default value of
`1.0f`.

Sema will modify the variable to be `static` (giving it internal linkage) and
change its initializer to be a call to a new built-in
`__builtin_get_spirv_spec_constant`. This built-in takes the specialization
constant ID and the default value as parameters. The AST for this variable would
be:

```
|-VarDecl 0x5595791c2960 <vk.spec-constant.hlsl:1:24, col:50> col:36 used my_constant 'const hlsl_private float' static cinit
| |-CallExpr 0x5595791c2e58 <col:50> 'float'
| | |-ImplicitCastExpr 0x5595791c2e40 <col:50> 'float (*)(unsigned int, float) noexcept' <FunctionToPointerDecay>
| | | `-DeclRefExpr 0x5595791c2da8 <col:50> 'float (unsigned int, float) noexcept' lvalue Function 0x5595791c2b50 '__builtin_get_spirv_spec_constant_float' 'float (unsigned int, float) noexcept'
| | |-ImplicitCastExpr 0x5595791c2e90 <col:3> 'unsigned int' <IntegralCast>
| | | `-IntegerLiteral 0x5595791c2a60 <col:3> 'int' 0
| | `-FloatingLiteral 0x5595791c2a40 <col:50> 'float' 1.000000e+00
| `-HLSLVkConstantIdAttr 0x5595791c29c8 <col:3, col:20> 0
```

During code generation, this built-in will be replaced with a call to the
existing SPIR-V builtin, `__spirv_SpecConstant`, which has the same semantics:

```
llvm @_ZL11my_constant = internal addrspace(10) global float 0.000000e+00, align 4
...
define internal spir_func void @__cxx_global_var_init() #4 {
entry:
  %0 = call token @llvm.experimental.convergence.entry()
  %1 = call float @_Z20__spirv_SpecConstantif(i32 0, float 1.000000e+00)
  store float %1, ptr addrspace(10) @_ZL11my_constant, align 4, !tbaa !3
  %2 = call ptr @llvm.invariant.start.p10(i64 4, ptr addrspace(10) @_ZL11my_constant)
  ret void
}
```

Note that the mangled name for `__spirv_SpecConstant` must be used in case there
a multiple specialization constants with different types.

The SPIR-V backend will lower the LLVM intrinsic to the appropriate
`OpSpecConstant*` instruction (e.g., OpSpecConstant for scalar floats) along
with an `OpDecorate` instruction for the SpecId.

```
OpDecorate %10 SpecId 0
%10 = OpSpecConstant %4 1065353216 ; float 1.0
```

## Alternatives considered

### Add a target attribute or metadata to the variable

We considered adding a target attribute or metadata to the variable to indicate
to the backend that it is a specialization constant. We decided against this
solution because a variable can be used in ways that a SPIR-V specialization
constant (which is an OpSpecConstant* result, not a variable in memory) cannot.
For example, an OpSpecConstant itself is not "loaded" from memory; its value is
used directly. Modeling this as a variable in the backend without a specific
intrinsic would require special handling for all uses of such variables, making
the design error-prone as every LLVM instruction interacting with it would need
to be aware of its special nature. The intrinsic approach makes the source of
the value explicit.

### Using the SPIR-V builtin during SEMA

We considered add a call to the SPIR-V builtin recognized by the backend
directly during SEMA. This was considered less desirable incase there is a
future backend that want to implement the feature, but not have to use the same
builtin. The design we used places the specific code went in CodeGen.

