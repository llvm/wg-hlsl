---
title: "[NNNN] - Local Resources Behavior"
params:
  status: Under Consideration
  authors:
    - bob80905: Joshua Batista
---

* Issues:
  [#180](https://github.com/llvm/wg-hlsl/issues/180)
* PRs:
  [#190037](https://github.com/llvm/llvm-project/pull/190037)

## Introduction

Local resource variables — resource handles declared within function scope
rather than at global scope — are a common pattern in HLSL shaders. Despite
their widespread use, the semantics around initialization, assignment,
aliasing, and control flow have historically been under-documented and
inconsistently handled across compilers. This proposal establishes, for each
local-resource pattern, what the HLSL specification ought to require (the
"ought" claim) and compares Clang's and DXC's current behavior against
that claim. Patterns whose specified behavior is not yet settled are
flagged as TBD so the relevant HLSL spec issues can be filed.

## Motivation

DXC has never had structured test coverage for local resource patterns. Many
valid and invalid usage patterns were left untested. Without a clear
specification, compiler implementers cannot distinguish correct behavior 
from bugs, and users cannot predict which patterns are safe to rely on.

This proposal aims to:

1. **Establish expected behavior** for each local-resource pattern,
   grounded in the HLSL specification rather than in any one compiler's
   current behavior.
2. **Compare Clang's and DXC's current behavior** against the expected
   behavior so that compiler-side bugs (in either compiler) and spec
   gaps can be told apart and tracked separately.
3. **Enable regression testing** so that future compiler changes can be
   validated against the expected behavior, and so that XFAILed tests
   point back to the appropriate compiler bug or spec issue.

> **Note:** Two pre-existing multi-function test files directly under the
> SemaHLSL directory (`local_resource_bindings.hlsl` and
> `local_resource_bindings_errs.hlsl`, landed via PR #182101) were consumed
> by this work. Their individual test functions were extracted into isolated
> per-pattern files under `Resources/Local-Resources/`, and the originals
> were deleted.

## Proposed solution

Each local-resource pattern is documented below in a per-category
"ought" table with the following columns:

- **Test** — the test file name (without the `.hlsl` extension) that
  exercises the pattern.
- **Behavior** — a concise description of the pattern, unique among all
  rows.
- **Ought Compile** — what the HLSL specification ought to require at
  compile time: `Clean`, `Warning`, `Error`, or `TBD / unspecified` when
  the spec has not yet decided. A `†` after the value indicates the
  claim is reasoned from analogous language rules but not yet pinned to
  a written HLSL spec proposal (i.e. maybe should be TBD); it is a
  candidate to be relaxed to `TBD / unspecified` if the spec working
  group disagrees.
- **Ought Runtime** — what the shader ought to do at runtime if it
  compiles, or `N/A` when a compile error is expected. A `†` here has
  the same meaning as on Ought Compile.
- **Clang** / **DXC** — ✅ if the compiler's current behavior matches the
  ought claim; ❌ followed by the actual behavior otherwise. A ❌ marks
  either a compiler bug or, when the ought claim is itself uncertain, a
  spec issue that needs to be resolved.

### Basic Local Resource Operations

> ✅ = currently matches the "ought" claim. ❌ = does not match (actual
> behavior in parentheses).

| Test | Behavior | Ought Compile | Ought Runtime | Clang | DXC |
|------|----------|---------------|---------------|-------|-----|
| `local_resource_alias_global` | Initialize a local from a single global, then Store through the local | Clean | Store reaches the global's binding | ✅ | ✅ |
| `local_resource_alias_chain` | Chain `a=g; b=a; c=b` then use `c` | Clean | Store reaches the global's binding | ✅ | ✅ |
| `local_resource_copy_between_locals` | `a=g; b=a` then use `b` | Clean | Store reaches the global's binding | ✅ | ✅ |
| `local_resource_self_assign` | `buf = buf` on an initialized local (no-op) | Clean | No state change beyond explicit operations | ✅ | ✅ |
| `local_resource_self_assign_uninitialized` | `Out = Out` where `Out` is an uninitialized `out` parameter | Error † (use of uninitialized resource handle) | N/A | ❌ Clean (no diagnostic) | ❌ Codegen error: *"local resource not guaranteed to map to unique global resource"* |
| `local_resource_reassign_same_global` | `if(c) buf=g; else buf=g;` (both branches assign the same global) | Clean | Store reaches `g` | ✅ | ✅ |
| `return_local_resource_initialized` | Return a local that aliases a global | Clean | Caller observes the global | ✅ | ✅ |
| `return_local_resource_uninitialized` | Return an uninitialized local | Error † (use of uninitialized resource handle) | N/A | ❌ Clean | ❌ Clean |
| `expression_init` | Initialize via a parenthesized ternary whose branches resolve to a single global | Clean | Store reaches the global | ✅ | ✅ |
| `local_resource_aggregate_init` | Aggregate-initialize a struct whose resource member is a global | Clean | Store reaches the global | ✅ | ✅ |
| `local_resource_multi_decl` | `RWByteAddressBuffer a=g0, b=g1` (two decls in one statement) | Clean | Stores reach the respective globals | ✅ | ✅ |
| `local_resource_default_init_store` | `RWByteAddressBuffer buf; buf.Store(...)` (no initializer, unbound handle) | Error † (use of uninitialized resource handle) | N/A | ❌ Clean (sema); DXIL Op Lowering assertion at codegen | ❌ Codegen error: *"local resource not guaranteed to map to unique global resource"* |
| `local_resource_conditional_single_path_assign` | `if(c) buf=g;` then `buf.Store(...)` (uninitialized on the else path) | Error † (possibly-uninitialized use) | N/A | ❌ Clean | ❌ Codegen error: *"local resource not guaranteed to map to unique global resource"* |
| `local_resource_comma_init` | `buf = (g0, g1)` — comma expression initializer | Warning † (left operand discarded) | Store reaches `g1` | ✅ Warning: *"left operand of comma operator has no effect"* | ✅ Warning: *"comma expression used where a constructor list may have been intended"* |

### Parameter Passing

| Test | Behavior | Ought Compile | Ought Runtime | Clang | DXC |
|------|----------|---------------|---------------|-------|-----|
| `local_resource_out_param` | Resource passed as `out` parameter, assigned in callee, read by caller | Clean | Caller observes the assigned resource | ✅ | ✅ |
| `local_resource_inout_param` | Resource passed as `inout` parameter; mutation in callee is visible to caller | Clean | Caller observes mutated state | ✅ | ✅ |
| `local_resource_const_param` | Resource passed as `const` parameter; `Store` invoked inside callee | Error † (Store mutates state through a `const`-qualified handle) | N/A | ✅ Error: *"no matching member function"* (`Store` not `const`-qualified) | ❌ Clean (silently accepts Store on a `const` resource) |

### Struct and Array Patterns

| Test | Behavior | Ought Compile | Ought Runtime | Clang | DXC |
|------|----------|---------------|---------------|-------|-----|
| `local_struct_resource_member` | Use a resource that is a struct member | Clean | Store reaches the global | ✅ | ✅ |
| `struct_array_with_resource_member` | Array of structs, each containing a resource member | Clean | Store reaches the indexed global | ✅ | ✅ |
| `struct_with_resource_array_member` | Struct containing an array of resources | Clean | Store reaches the indexed global | ✅ | ✅ |
| `nested_struct_resource_member` | Inner/outer nested struct with a resource | Clean | Store reaches the global | ✅ | ✅ |
| `local_resource_array` | Plain local array of resources initialized from globals | Clean | Store reaches the indexed global | ✅ | ✅ |
| `local_resource_array_copy` | Copy one local resource array to another, then Store through the copy | Clean | Stores reach the original globals | ✅ | ✅ |
| `local_resource_array_dynamic_index` | Dynamic (runtime) index into a local resource array | Clean | Store reaches the dynamically-indexed global | ❌ Clean (sema); DXIL Legalizer assertion at codegen | ✅ |
| `local_resource_array_partial_init` | `{g0}` for a 2-element resource array (second element default-initialized) | Error † (every array element must be bound to a global) | N/A | ❌ Clean (sema); DXIL Legalizer assertion at codegen | ❌ Clean |
| `local_resource_array_size_one` | Resource array of size 1 | Clean | Store reaches the global | ✅ | ✅ |
| `struct_resource_member_reassign` | Reassign a struct's resource member to a different global | Warning † (binding-ambiguous reassignment) | Store reaches the most-recently-assigned global | ✅ Warning (`-Whlsl-explicit-binding`) | ❌ Clean (no diagnostic) |
| `local_resource_struct_return` | Function returns a struct containing a resource | Clean | Caller observes the returned resource | ✅ | ✅ |
| `local_resource_mixed_struct` | Struct with both a resource member and a scalar member | Clean | Operations reach both members independently | ✅ | ✅ |
| `local_resource_struct_method` | Struct with a member function that operates on a resource member | Clean | Store reaches the global via the member function | ✅ | ✅ |

### Control Flow

| Test | Behavior | Ought Compile | Ought Runtime | Clang | DXC |
|------|----------|---------------|---------------|-------|-----|
| `local_resource_shadow_inner_scope` | Local resource shadowed by another local in an inner block | Clean | Inner-scope Store reaches inner global; outer Store reaches outer global | ✅ | ✅ |
| `local_resource_block_lifetime` | Resource assigned in inner block, used in outer scope | Clean | Store reaches the assigned global | ✅ | ✅ |
| `local_resource_nested_blocks_reassign` | Reassigned to a different global across nested blocks | Warning † (binding-ambiguous reassignment) | Store reaches the most-recently-assigned global | ✅ Warning (`-Whlsl-explicit-binding`) | ❌ Clean |
| `local_resource_early_return_reassign` | Reassigned to a different global on an early-return path | Warning † (binding-ambiguous reassignment) | Store reaches the assigned global per taken path | ✅ Warning (`-Whlsl-explicit-binding`) | ❌ Clean |
| `local_resource_unreachable_reassign` | Reassigned in provably unreachable code | Warning † (binding-ambiguous reassignment; possibly also dead-code warning) | Store reaches the original global (unreachable code does not execute) | ✅ Warning (`-Whlsl-explicit-binding`) | ❌ Clean |
| `local_resource_switch_reassign` | Reassigned to a different global inside switch cases | Warning † (binding-ambiguous reassignment) | Store reaches the per-case-assigned global | ✅ Warning (`-Whlsl-explicit-binding`) | ❌ Clean |
| `local_resource_switch_fallthrough` | Switch with case fallthrough reassigning the resource | Warning † (binding-ambiguous reassignment) | Store reaches the global from the last assignment along the taken path | ✅ Warning (`-Whlsl-explicit-binding`) | ❌ Clean |
| `local_resource_switch_default` | Switch with explicit `default:` case reassigning the resource | Warning † (binding-ambiguous reassignment) | Store reaches the per-case-assigned global | ✅ Warning (`-Whlsl-explicit-binding`) | ❌ Clean |

### Loop Patterns

| Test | Behavior | Ought Compile | Ought Runtime | Clang | DXC |
|------|----------|---------------|---------------|-------|-----|
| `loop_var` | Resource declared in a for-loop initializer | Clean | Per-iteration Store reaches the same global | ✅ | ✅ |
| `local_resource_loop_array_index` | Pick resource from a global array inside a loop using loop index | Clean | Per-iteration Store reaches the indexed global | ✅ | ✅ |
| `local_resource_nested_loops` | Pick resource from a global array inside nested loops | Clean | Per-iteration Store reaches the indexed global | ✅ | ✅ |
| `local_resource_loop_carried` | Loop-carried local reassigned from array each iteration | Warning † (binding-ambiguous reassignment) | Store reaches per-iteration indexed global | ✅ Warning (`-Whlsl-explicit-binding`) | ❌ Clean |
| `local_resource_do_while_reassign` | Reassign local to a different global inside a `do-while` body | Warning † (binding-ambiguous reassignment) | Store reaches the assigned global per iteration | ✅ Warning (`-Whlsl-explicit-binding`) | ❌ Clean |
| `local_resource_break_reassign` | Reassign local to a different global immediately before `break` | Warning † (binding-ambiguous reassignment) | Store after the loop reaches the global assigned at break | ✅ Warning (`-Whlsl-explicit-binding`); DXIL Op Lowering assertion at codegen | ❌ Codegen error: *"local resource not guaranteed to map to unique global resource"* |
| `local_resource_continue_reassign` | Reassign local to a different global immediately before `continue` | Warning † (binding-ambiguous reassignment) | Subsequent iterations observe the reassigned global | ✅ Warning (`-Whlsl-explicit-binding`) | ❌ Codegen error: *"local resource not guaranteed to map to unique global resource"* |

### Reassignment and Phi/Merge

| Test | Behavior | Ought Compile | Ought Runtime | Clang | DXC |
|------|----------|---------------|---------------|-------|-----|
| `local_resource_reassign_different_global` | Plain reassignment of a local to a different global | Warning † (binding-ambiguous reassignment) | Store reaches the most-recently-assigned global | ✅ Warning (`-Whlsl-explicit-binding`) | ❌ Clean |
| `local_resource_deep_phi` | Nested if/else with ternary that merges multiple globals (deep phi) | Warning † (binding-ambiguous reassignment) | Store reaches the path-selected global | ✅ Warning (`-Whlsl-explicit-binding`) | ❌ Clean |
| `local_resource_ternary_lvalue` | Ternary expression used as an lvalue (`cond ? a : b = g`) | TBD / unspecified | TBD / unspecified | ✅ Clean | ❌ ICE (internal compiler error) |
| `local_resource_swap` | Swap two locals through a temporary | Clean | Each local ends up holding the other's original global | ✅ | ✅ |

### Bindless

| Test | Behavior | Ought Compile | Ought Runtime | Clang | DXC |
|------|----------|---------------|---------------|-------|-----|
| `local_resource_bindless_array` | Dynamic (runtime) index into a global resource array | Clean | Store reaches the dynamically-indexed global | ✅ | ✅ |
| `local_resource_bindless_selection` | Multiple dynamic indices into a global resource array | Clean | Each Store reaches its dynamically-indexed global | ✅ | ✅ |

### Function Forwarding and Multiple Uses

| Test | Behavior | Ought Compile | Ought Runtime | Clang | DXC |
|------|----------|---------------|---------------|-------|-----|
| `local_resource_forward_through_functions` | Resource forwarded through a chain of helper function calls | Clean | Store at the chain's leaf reaches the original global | ✅ | ✅ |
| `local_resource_with_wave_intrinsic` | Local resource used alongside wave intrinsics (e.g. `WaveActiveSum`) | Clean | Store reaches the global, wave intrinsics return expected values | ✅ | ✅ |
| `local_resource_multiple_uses` | Same local resource passed to multiple helpers in one entry point | Clean | Each helper's Store reaches the global | ✅ | ✅ |
| `local_resource_from_function_return` | Local initialized from a function that returns a single global | Clean | Store reaches the returned global | ✅ | ✅ |
| `local_resource_multiple_returns` | Helper reassigns local then returns it across two `return` statements | Warning † (binding-ambiguous reassignment inside helper) | Caller observes the helper's per-path global | ✅ Warning (`-Whlsl-explicit-binding`) | ❌ Codegen error: *"local resource not guaranteed to map to unique global resource"* |
| `local_resource_multi_return_paths` | Helper has two `return` statements that return distinct globals; caller initializes a local from the helper's return value | Warning † (call expression yields a binding-ambiguous result) | Caller observes one of the two globals per call | ❌ Clean (no warning fires: initializer is a call expression, not a global reference) | ❌ Codegen error at the first `return` inside the helper |
| `local_resource_template_function` | Template function deducing the resource type from the argument | Clean | Store inside template reaches the global | ✅ | ✅ |
| `local_resource_chained_call` | Method invoked directly on a function's return value (`GetBuf().Store(...)`) | Clean | Store reaches the returned global | ✅ | ✅ |
| `local_resource_overload` | Function overloaded by resource type; correct overload selected for the local | Clean | Selected overload's Store reaches the global | ✅ | ✅ |

### Static and Storage

| Test | Behavior | Ought Compile | Ought Runtime | Clang | DXC |
|------|----------|---------------|---------------|-------|-----|
| `local_resource_static_local` | `static RWByteAddressBuffer buf = g;` inside a function | Clean | Store reaches the global; the binding persists across calls | ✅ | ❌ ICE: `llvm::cast<X>()` argument of incompatible type |

### Type Mixing and Alternative Resource Types

| Test | Behavior | Ought Compile | Ought Runtime | Clang | DXC |
|------|----------|---------------|---------------|-------|-----|
| `local_resource_different_types` | Two different resource types (`RWByteAddressBuffer` + `RWStructuredBuffer`) coexist in the same function | Clean | Each resource's operation reaches its respective global | ✅ | ✅ |
| `local_resource_read_only` | Local `ByteAddressBuffer` (read-only SRV) initialized from a global, Loaded from | Clean | Load returns the bound global's contents | ✅ | ✅ |
| `local_resource_structured_buffer` | Local `RWStructuredBuffer<uint>` with subscript-store access | Clean | Subscript-store reaches the global at the given index | ✅ | ✅ |

### Invalid Type Operations

| Test | Behavior | Ought Compile | Ought Runtime | Clang | DXC |
|------|----------|---------------|---------------|-------|-----|
| `local_resource_arithmetic` | Arithmetic on a resource handle (`buf + 1`) | Error (no arithmetic on resources) | N/A | ✅ Error: *"invalid operands to binary expression"* | ✅ Error: *"scalar, vector, or matrix expected"* |
| `local_resource_addition` | Add two resource handles (`buf + buf`) | Error (no arithmetic on resources) | N/A | ✅ Error: *"invalid operands to binary expression"* | ✅ Error: *"scalar, vector, or matrix expected"* |
| `local_resource_compare` | Equality comparison between two resources (`a == b`) | Error (no equality on resources) | N/A | ✅ Error: *"invalid operands to binary expression"* | ✅ Error: *"scalar, vector, or matrix expected"* |
| `local_resource_to_bool` | Implicit conversion of a resource to `bool` | Error (no conversion to bool) | N/A | ✅ Error: *"no viable conversion"* | ✅ Error: *"cannot convert"* |
| `local_resource_cast_to_uint` | C-style cast of a resource to `uint` | Error (no conversion to scalar) | N/A | ✅ Error: *"cannot convert"* | ✅ Error: *"cannot convert"* |
| `local_resource_cast_sampler_to_buffer` | C-style cast from `SamplerState` to `RWByteAddressBuffer` | Error (incompatible resource types) | N/A | ✅ Error: *"no matching conversion"* | ✅ Error: type mismatch |
| `local_resource_assign_wrong_type` | Assign `RWStructuredBuffer` to `RWByteAddressBuffer` | Error (incompatible resource types) | N/A | ✅ Error: *"no viable overloaded '='"* | ✅ Error: type mismatch |
| `local_resource_const_reassign` | Reassign a `const`-qualified local resource | Error (cannot assign to `const`) | N/A | ✅ Error: *"cannot assign to variable with const-qualified type"* + Warning (`-Whlsl-explicit-binding`) | ✅ Error: *"cannot assign to const"* |
| `local_resource_volatile` | `volatile` qualifier on a resource; method call invoked on it | Error † (methods are not `volatile`-qualified) | N/A | ✅ Error: *"no matching member function"* | ❌ Clean (silently accepts `volatile` on resources) |
| `local_resource_static_const` | `static const` local resource with `Load` method call | Error † (`Load` not `const`-qualified) | N/A | ✅ Error: *"no matching member function"* | ❌ ICE |
| `local_resource_static_const_store` | `static const` local resource with `Store` method call | Error † (`Store` not `const`-qualified) | N/A | ✅ Error: *"no matching member function"* | ❌ ICE |
| `local_resource_lambda_capture` | Lambda captures a local resource by value and calls `Store` on it | TBD / unspecified (HLSL lambda capture semantics for resources are not yet specified) | TBD | ❌ (under proposed spec) Error: *"no matching member function"* (captured resource treated as `const` in lambda body) | ❌ Parse error: *"expected expression"* (lambdas not supported) |

### Invalid Declarations

| Test | Behavior | Ought Compile | Ought Runtime | Clang | DXC |
|------|----------|---------------|---------------|-------|-----|
| `local_resource_default_param` | Function parameter with a default value followed by a parameter without one | Error (defaulted parameters must be trailing) | N/A | ✅ Error: *"missing default argument on parameter"* | ✅ Error: *"missing default argument on parameter"* |
| `local_resource_as_structured_buffer_element` | Resource type used as the element type of `RWStructuredBuffer<T>` (intangible) | Error (resource types cannot be element types) | N/A | ✅ Error: *"constraints not satisfied for class template"* | ✅ Error: *"is an object and cannot be used as a type parameter"* |
| `local_resource_zero_init` | Brace zero-initialization of a local resource (`= {}`) | Error (resource has no zero/null representation) | N/A | ✅ Error: empty initializer list | ✅ Error: empty initializer list |
| `local_resource_array_oob` | Compile-time out-of-bounds index into a resource array | Error (OOB constant index) | N/A | ❌ Warning (`-Warray-bounds`) | ✅ Error: *"array index N is out of bounds"* |
| `local_resource_explicit_register` | Explicit `register()` attribute on a local resource variable | Error (`register` only applies to globals) | N/A | ✅ Error: *"'register' attribute only applies to cbuffer/tbuffer and external global variables"* | ❌ Clean (silently ignores the local `register()`) |

### Ternary Conditional Resource Assignment (CodeGen)

These patterns construct a local resource whose binding depends on
runtime control flow. The "ought" claim throughout this section is that
the assignment is well-formed but binding-ambiguous, so a warning should
be emitted and the runtime behavior is to access whichever global the
control flow selected. Patterns where both ternary branches resolve to
the same binding are unambiguous and should compile clean.

| Test | Behavior | Ought Compile | Ought Runtime | Clang | DXC |
|------|----------|---------------|---------------|-------|-----|
| `local_resource_ternary_assign` | `buf = cond ? g0 : g1;` after declaration | Warning † (binding-ambiguous reassignment) | Store reaches `g0` or `g1` per `cond` | ✅ Warning (`-Whlsl-explicit-binding`) | ❌ Codegen error: *"local resource not guaranteed to map to unique global resource"* |
| `local_resource_ternary_as_argument` | Pass `cond ? g0 : g1` directly as a function argument | Warning † (binding-ambiguous argument) | Callee Store reaches `g0` or `g1` per `cond` | ❌ Clean (no warning fires for ternary at call site) | ❌ Codegen error: *"local resource not guaranteed to map to unique global resource"* |
| `local_resource_nested_ternary` | `c1 ? g0 : (c2 ? g1 : g2)` | Warning † (binding-ambiguous reassignment) | Store reaches one of `g0`/`g1`/`g2` per conditions | ✅ Warning (`-Whlsl-explicit-binding`) | ❌ Codegen error (2 errors, one per ternary level) |
| `local_resource_conditional_reassign_different_global` | `if(cond) out = g1;` reassigning an output resource | Warning † (binding-ambiguous reassignment) | Store reaches `g0` or `g1` per `cond` | ✅ Warning (`-Whlsl-explicit-binding`) | ❌ Codegen error: *"local resource not guaranteed to map to unique global resource"* |
| `local_resource_conditional_reassign_from_array` | `if(cond) out = arr[i];` (conditional reassign from unbounded resource array) | Warning † (binding-ambiguous reassignment) | Store reaches either the original global or `arr[i]` per `cond` | ✅ Warning (`-Whlsl-explicit-binding`) | ❌ Codegen error: *"local resource not guaranteed to map to unique global resource"* |
| `local_resource_static_ternary_assign` | Ternary assigning to a `static` local resource (lib target) | Warning † (binding-ambiguous reassignment) | Store reaches the selected global; the binding persists across calls | ✅ Warning (`-Whlsl-explicit-binding`) | ❌ Codegen errors: *"non const static global resource use is disallowed"* + *"local resource not guaranteed to map to unique global resource"* |
| `local_resource_ternary_both_same` | `cond ? g0 : g0` (both branches the same global) | Clean | Store reaches `g0` | ✅ | ✅ |
| `local_resource_ternary_same_array_elements` | `cond ? arr[0] : arr[1]` (both branches same global array) | Clean | Store reaches the selected array element | ✅ | ✅ |
| `local_resource_if_else_array_elements` | `if(cond) buf = arr[0]; else buf = arr[1];` | Clean | Store reaches the selected array element | ✅ | ✅ |

### Wave-Conditional Reassignment (CodeGen)

| Test | Behavior | Ought Compile | Ought Runtime | Clang | DXC |
|------|----------|---------------|---------------|-------|-----|
| `local_resource_wave_uniform` | Local resource reassigned under wave-conditional control flow (`if(WaveIsFirstLane()) buf = g1;`) | Warning † (binding-ambiguous reassignment) | Each lane's Store reaches the global selected on its path | ✅ Warning (`-Whlsl-explicit-binding`) | ❌ Codegen error: *"local resource not guaranteed to map to unique global resource"* |

### Groupshared Resources

| Test | Behavior | Ought Compile | Ought Runtime | Clang | DXC |
|------|----------|---------------|---------------|-------|-----|
| `use_groupshared` | Pass a `groupshared` resource as a function argument | Error † (resources cannot live in groupshared address space) | N/A | ✅ Error (constructor mismatch on groupshared argument) | ✅ Validation error |
| `use_groupshared_direct_store` | Call `Store` directly on a `groupshared` resource | Error † (resources cannot live in groupshared address space) | N/A | ✅ Error (address-space mismatch on `this`) | ✅ Validation error |
| `use_struct_groupshared` | Access a resource from a `groupshared` struct | Error † (resources cannot live in groupshared address space) | N/A | ❌ Clean (currently silent — see TODO in test) | ✅ Validation error |

## Key Behavioral Themes

### Ambiguous Binding: Sema Warning vs. CodeGen Error

A recurring pattern across the tables above is a local resource whose
binding cannot be resolved to a single unique global at compile time
(reassignment across control flow, ternary merges, loop-carried
reassignment, etc.). The expected behavior is a compile-time diagnostic
that surfaces the ambiguity to the user. Clang emits
`-Whlsl-explicit-binding` at sema for these patterns. DXC has no
equivalent sema diagnostic — it either silently accepts the pattern
(producing implementation-defined runtime behavior) or rejects it as a
hard error during its `DxilCondenseResources` codegen pass. Neither
behavior is the spec-defined baseline; the ought-tables flag both
deviations.

### DXC ICEs on Static and Const-Static Resources

DXC asserts internally on `static` local resources and `static const`
resources. These are compiler bugs, not intentional behavior.

### Texture2D vs RWByteAddressBuffer

Some behaviors differ between resource types. DXC ICEs with both
`static Texture2D` and `static RWByteAddressBuffer`. The test suite
uses `RWByteAddressBuffer` because Clang does not yet support `Texture2D`.

## Test Placement

Test placement follows from each row's "Ought Compile" column above, not
from which compiler currently passes or fails:

- Shaders that **ought to compile without error** (Clean or Warning)
  belong in the
  [offload test suite](https://github.com/llvm/offload-test-suite)
  under `test/Feature/LocalResources/`, so that runtime behavior on real
  GPU hardware and software rasterizers can be validated against the
  expected runtime behavior. Tests for which a compiler's current
  behavior disagrees with the Ought column are XFAILed against an
  appropriate tracking issue.
- Shaders that **ought to fail compilation with an error** belong
  somewhere in the clang tree (typically `SemaHLSL/`), where `-verify`
  can pin the expected diagnostic. They are not added to the offload
  test suite regardless of any current compiler's behavior.
- Shaders whose Ought claim is **TBD / unspecified** are blocked on
  spec work; this document is the place to surface those gaps so the
  HLSL spec issues can be filed.

## Alternatives considered

**Document only observed behavior, without ought claims.** An earlier
draft of this proposal listed Clang and DXC behavior side-by-side
without expressing what either compiler ought to do. That approach was
rejected because it leaves no way to tell a compiler bug apart from
correct behavior, makes XFAIL decisions ad-hoc, and forces the
ought-discussion to happen scattered across individual test PRs rather
than as a single comprehensive survey. The current per-row ought claim
makes spec gaps explicit (via `TBD / unspecified`) and gives every ❌
a clear next step: either fix the compiler or file a spec issue.

**Organize tests by which compiler currently passes.** An earlier
draft used subdirectories named `ClangPass-DXCCodegenError/`,
`DXCPass-ClangSemaError/`, etc. That structure bakes current compiler
behavior into the file layout, which would require moving tests every
time a compiler changes. The Ought-driven placement described in
[Test Placement](#test-placement) is stable against compiler fixes.

## Acknowledgments

Helena Kotas, Justin Bogner