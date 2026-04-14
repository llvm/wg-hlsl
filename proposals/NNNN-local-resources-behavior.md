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
inconsistently handled across compilers. This proposal documents the expected
behavior for DXC when handling local resource variables and identifies key
behavioral differences between DXC and Clang.

## Motivation

DXC has never had structured test coverage for local resource patterns. Many
valid and invalid usage patterns were left untested. Without a clear
specification, compiler implementers cannot distinguish correct behavior 
from bugs, and users cannot predict which patterns are safe to rely on.

This proposal aims to:

1. **Establish a reference** for how DXC handles each local resource pattern.
2. **Document behavioral differences** between DXC and Clang, particularly
   where DXC issues hard errors for patterns that Clang treats as warnings
   or accepts silently.
3. **Enable regression testing** so that future compiler changes can be
   validated against well-defined expectations.

## Proposed solution

The observed behavior for local resource variables is documented below,
organized by category. Each pattern includes the observed behavior for
both DXC and Clang.

### Basic Local Resource Operations

| Pattern | DXC | Clang |
|---------|-----|-------|
| Alias from global (`buf = gBuf0`) | Clean | Clean |
| Alias chain (`a = g; b = a; c = b`) | Clean | Clean |
| Copy between locals (`a = g; b = a`) | Clean | Clean |
| Self-assignment (`buf = buf`) | Clean | Clean |
| Return initialized local | Clean | Clean |
| Return uninitialized local | Clean | Clean |
| Parenthesized ternary expression init | Clean | Clean |
| Aggregate init of struct with resource | Clean | Clean |
| Two resources in a single declaration | Clean | Clean |
| Use of uninitialized local resource | Clean | Clean |
| Default-init store (unbound handle) | Error (codegen): *"local resource not guaranteed to map to unique global resource"* | **Clean** |
| Conditional init (`if(cond) buf = g;`) | Error (codegen): *"local resource not guaranteed to map to unique global resource"* | **Clean** |
| Comma expression init (`(gBuf0, gBuf1)`) | **Clean** | Warning: *"left operand of comma operator has no effect"* |

### Parameter Passing

| Pattern | DXC | Clang |
|---------|-----|-------|
| Resource as `out` parameter | Clean | Clean |
| Resource as `inout` parameter | Clean | Clean |
| Resource as `const` parameter | Clean | Clean |

### Struct and Array Patterns

| Pattern | DXC | Clang |
|---------|-----|-------|
| Struct with a resource member | Clean | Clean |
| Array of structs each containing a resource | Clean | Clean |
| Struct containing an array of resources | Clean | Clean |
| Nested struct with resource | Clean | Clean |
| Deeply composed struct layers with resource | Clean | Clean |
| Plain local array of resources | Clean | Clean |
| Copy of local resource arrays | Clean | Clean |
| Dynamic index into a local resource array | Clean | Clean |
| Partially initialized resource array | Clean | Clean |
| Size-one resource array (edge case) | Clean | Clean |
| Reassign a struct's resource member | Clean | Clean |
| Function returning a struct with a resource | Clean | Clean |
| Struct with resource + scalar member | Clean | Clean |
| Struct with member function using a resource | Clean | Clean |

### Control Flow

| Pattern | DXC | Clang |
|---------|-----|-------|
| Shadowed resource in inner block | Clean | Clean |
| Assigned in inner block, used in outer scope | Clean | Clean |
| Reassign across nested blocks | **Clean** | Warning (`-Whlsl-explicit-binding`) |
| Reassign after early return path | **Clean** | Warning (`-Whlsl-explicit-binding`) |
| Reassign in unreachable code | **Clean** | Warning (`-Whlsl-explicit-binding`) |
| Reassign in switch cases | **Clean** | Warning (`-Whlsl-explicit-binding`) |
| Switch with fallthrough reassignment | **Clean** | Warning (`-Whlsl-explicit-binding`) |
| Switch with explicit default reassignment | **Clean** | Warning (`-Whlsl-explicit-binding`) |

### Loop Patterns

| Pattern | DXC | Clang |
|---------|-----|-------|
| Resource as a for-loop variable | Clean | Clean |
| Resource from array inside a loop | Clean | Clean |
| Resource from array in nested loops | Clean | Clean |
| Loop-carried reassignment from array | **Clean** | Warning (`-Whlsl-explicit-binding`) |
| Reassignment inside a do-while loop | **Clean** | Warning (`-Whlsl-explicit-binding`) |

### Reassignment and Phi/Merge

| Pattern | DXC | Clang |
|---------|-----|-------|
| Reassign to a different global | **Clean** | Warning (`-Whlsl-explicit-binding`) |
| Nested if/else with ternary (deep phi) | **Clean** | Warning (`-Whlsl-explicit-binding`) |
| Ternary expression as lvalue | **ICE** (internal compiler error) | Clean |
| Swap two locals through a temporary | Clean | Clean |

### Bindless

| Pattern | DXC | Clang |
|---------|-----|-------|
| Dynamic index into global resource array | Clean | Clean |
| Multiple dynamic array selections | Clean | Clean |

### Function Forwarding and Multiple Uses

| Pattern | DXC | Clang |
|---------|-----|-------|
| Resource passed through a call chain | Clean | Clean |
| Resource used alongside wave intrinsics | Clean | Clean |
| Same local resource passed to multiple helpers | Clean | Clean |
| Local resource initialized from function return | Clean | Clean |
| Template function taking a resource parameter | Clean | Clean |
| Method on function return value (`GetBuf().Store(...)`) | Clean | Clean |
| Function overloading by resource type | Clean | Clean |

### Static and Storage

| Pattern | DXC | Clang |
|---------|-----|-------|
| Static local `RWByteAddressBuffer` | **ICE**: `llvm::cast<X>()` incompatible type | Clean |
| Static local `Texture2D` | **ICE** | N/A (not yet supported) |

### Type Mixing and Alternative Resource Types

| Pattern | DXC | Clang |
|---------|-----|-------|
| Two different resource types in same function | Clean | Clean |
| Read-only `ByteAddressBuffer` as local | Clean | Clean |
| `RWStructuredBuffer<uint>` with subscript access | Clean | Clean |

### Invalid Type Operations

| Pattern | DXC | Clang |
|---------|-----|-------|
| Arithmetic (`buf + 1`) | Error: *"scalar, vector, or matrix expected"* | Error: *"invalid operands to binary expression"* |
| Addition (`buf + buf`) | Error: *"scalar, vector, or matrix expected"* | Error: *"invalid operands to binary expression"* |
| Equality comparison (`a == b`) | Error: *"scalar, vector, or matrix expected"* | Error: *"invalid operands to binary expression"* |
| Implicit conversion to `bool` | Error: *"cannot convert"* | Error: *"no viable conversion"* |
| C-style cast to `uint` | Error: *"cannot convert"* | Error: *"cannot convert"* |
| Cast `SamplerState` to `RWByteAddressBuffer` | Error: type mismatch | Error: *"no matching conversion"* |
| Assign wrong type | Error: type mismatch | Error: *"no viable overloaded '='"* |
| `const` reassignment | Error: *"cannot assign to const"* | Error: *"cannot assign to variable with const-qualified type"* |
| `volatile` resource method call | **Clean** (silently accepts `volatile`) | Error: *"no matching member function"* |
| `static const` resource method call | **ICE** | Error: `Load`/`Store` not `const`-qualified |

### Invalid Declarations

| Pattern | DXC | Clang |
|---------|-----|-------|
| Resource param with default, followed by param without | Error | Error |
| Resource type as `RWStructuredBuffer` element (intangible) | Error | Error |
| Brace (zero) init `= {}` | Error: empty initializer list | Error: empty initializer list |
| Compile-time out-of-bounds array index | **Error** (hard error) | Warning (`-Warray-bounds`) |

### Ternary Conditional Resource Assignment (CodeGen)

DXC's `DxilCondenseResources` pass rejects patterns where a local
resource does not resolve to a single unique global resource. Clang
accepts these patterns, emitting a warning in most cases.

| Pattern | DXC | Clang |
|---------|-----|-------|
| Ternary init (`buf = cond ? g0 : g1`) | Error (codegen): *"local resource not guaranteed to map to unique global resource"* | Warning (`-Whlsl-explicit-binding`) |
| Ternary assignment post-declaration | Error (codegen) | Warning (`-Whlsl-explicit-binding`) |
| Ternary phi merge | Error (codegen) | Warning (`-Whlsl-explicit-binding`) |
| Ternary resource as function argument | Error (codegen) | **Clean** |
| Nested ternary (`c1 ? g0 : (c2 ? g1 : g2)`) | Error (codegen, 2 errors) | Warning (`-Whlsl-explicit-binding`) |

### Wave-Conditional Reassignment (CodeGen)

| Pattern | DXC | Clang |
|---------|-----|-------|
| Reassignment under wave-conditional control flow | Error (codegen): *"local resource not guaranteed to map to unique global resource"* | Warning (`-Whlsl-explicit-binding`) |

### Groupshared Resources

| Pattern | DXC | Clang |
|---------|-----|-------|
| Passing groupshared resource as argument | Validation error | Sema error (constructor mismatch) |
| Store on groupshared resource | Validation error | Sema error (address space mismatch) |
| Resource from groupshared struct | Validation error | Currently silent (expected to fail — see TODO) |

## Key Behavioral Themes

### DXC Defers to CodeGen Where Clang Warns at Sema

The most significant difference between the two compilers is their approach
to ambiguous resource bindings. Clang proactively warns at sema via
`-Whlsl-explicit-binding` when a local resource assignment does not resolve
to a single unique global resource. DXC has no equivalent sema diagnostic —
it either silently accepts the pattern or rejects it as a hard error during
its `DxilCondenseResources` codegen pass.

### DXC ICEs on Static and Const-Static Resources

DXC asserts internally on `static` local resources and `static const`
resources. These are compiler bugs, not intentional behavior.

### Texture2D vs RWByteAddressBuffer

Some behaviors differ between resource types. DXC ICEs with
`static Texture2D` but accepts `static RWByteAddressBuffer`. The test suite
uses `RWByteAddressBuffer` because Clang does not yet support `Texture2D`.

## Offload Test Suite

Tests that compile cleanly — producing a valid compiled output with no
errors or warnings on a given compiler — are candidates for the
[offload test suite](https://github.com/llvm/offload-test-suite) under
`test/Feature/LocalResources/`. The offload test suite executes shaders
at runtime against real GPU hardware and software rasterizers, validating
end-to-end correctness beyond what static compilation checks can verify.

### Inclusion criteria

A test is added to the offload test suite when **Clang produces a
compiled output** for it — that is, compilation succeeds with zero errors.
Tests that emit only warnings (e.g. `-Whlsl-explicit-binding`) still
produce compiled output and may qualify, but the primary set consists of
tests that are fully clean.

### Tests added

The **45 tests** that compile cleanly on both DXC and Clang are placed
directly in `test/Feature/LocalResources/`. These cover basic aliasing,
copies, parameter passing, structs, arrays, control flow, loops, bindless
access, function forwarding, and alternative resource types.

Two additional subdirectories capture tests that compile cleanly on only
one compiler:

- **`ClangPass/`** (4 tests) — clean on Clang, but DXC errors or ICEs.
  These include conditional init, default-init store, static local
  resources, and ternary lvalue assignment.
- **`DXCPass/`** (11 tests) — clean on DXC, but Clang emits
  `-Whlsl-explicit-binding` warnings or errors. These include reassignment
  patterns across control flow, switches, loops, and `volatile` resources.

Tests that produce errors on **both** compilers (invalid type operations,
bad declarations) are not included in the offload test suite since neither
compiler produces a compiled output for them.

## Alternatives considered

## Acknowledgments

Helena Kotas, Justin Bogner