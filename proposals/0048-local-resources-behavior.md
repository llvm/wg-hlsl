---
title: "[0048] - Local Resources Behavior"
params:
  status: Accepted
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
   validated against the expected behavior, and so that every row whose
   current behavior is wrong points back to a tracking compiler bug or
   spec issue.

> **Note:** Two pre-existing multi-function test files landed via PR
> #182101 (`local_resource_bindings.hlsl` and
> `local_resource_bindings_errs.hlsl`) were moved from directly under the
> SemaHLSL directory into `Resources/Local-Resources/` and renamed to
> `bindings.hlsl` and `bindings_errs.hlsl`. They are retained as
> multi-function files rather than split per-pattern, so their original
> cases stay together.

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

The **Clang** and **DXC** columns reflect *end-to-end* compilation —
sema plus codegen plus the backend's DXIL emission — not front-end-only
or `-emit-llvm` results. Each test name links to a Compiler Explorer
view that runs `dxc_trunk` and `hlsl_clang_trunk` side-by-side with
`-T <profile> -E <entry>` (no `-emit-llvm`, no `-verify`), so a reader
clicking the link sees exactly the invocation that produced the result
recorded in the table. This matters for binding-ambiguous patterns: a
`-verify` or `-emit-llvm` probe stops before DXIL emission and would
miss the codegen-stage error that both compilers raise from
`DxilCondenseResources` / equivalent.

### Assignment and Initialization Forms

> ✅ = currently matches the "ought" claim. ❌ = does not match (actual
> behavior in parentheses).

| Test | Behavior | Ought Compile | Ought Runtime | Clang | DXC |
|------|----------|---------------|---------------|-------|-----|
| [`consolidated_assignments`] | Chained aliasing/initialization forms — ternary initializer (constant and same-arm runtime conditions), struct aggregate init from a function return, direct init from a function return, a method called directly on a function return, alias chain, comma initializer, self-assign, dead-branch reassignment, and forwarding through a call chain — all resolving to one global | Clean | Every Store reaches the single global (`gBuf0`); `gBuf1`'s binding is folded away | ✅ | ✅ |

### Const-Qualified Locals

| Test | Behavior | Ought Compile | Ought Runtime | Clang | DXC |
|------|----------|---------------|---------------|-------|-----|
| [`const_local_store`] | `const RWByteAddressBuffer local = gBuf;` then `local.Store(...)` (also passes `local` to a callee doing `Load` on a `const RWByteAddressBuffer` parameter, which both compilers accept) | Clean (per `int *const` semantics: `const` qualifies the handle binding, not the buffer's mutability — `Store` should remain callable) | Store round-trips through the buffer; final value reaches the global | ❌ Error: *"no matching member function for call to 'Store'"* (clang treats `const` on the handle as forbidding non-`const` member calls, like a C++ `const T`) | ✅ Clean |

### Local Resource Arrays

| Test | Behavior | Ought Compile | Ought Runtime | Clang | DXC |
|------|----------|---------------|---------------|-------|-----|
| [`array`] | Two plain local resource arrays of different sizes (`Arr[2]` and `Arr2[1]`), each initialized from a distinct global, then Stored through at distinct offsets and values | Clean | Each element's Store reaches the corresponding global | ✅ | ✅ |
| [`array_partial_init_dynamic`] | 4-element local resource array with only `arr[0]` and `arr[1]` assigned, both from the same global; dynamic store `arr[tid.x & 1]` provably stays within the assigned elements | Clean (every reachable element resolves to the same unique global) | Store reaches `Out` | ❌ Sema clean, but codegen fails: *"Load of … is not a global resource handle"*, then asserts in `DXILLegalizePass` ([#192538](https://github.com/llvm/llvm-project/issues/192538)) | ✅ Clean |

### Binding Ambiguity Diagnostics

| Test | Behavior | Ought Compile | Ought Runtime | Clang | DXC |
|------|----------|---------------|---------------|-------|-----|
| [`branched_reassign_ambiguous`] | Local initialized from one global, then reassigned to a different global inside an `if` (`buf = gBuf1; if (cond) { buf = gBuf2; }`) — `buf` resolves to either global at the access site | Error † (binding-ambiguous reassignment that cannot be folded away) | N/A | ❌ Warning at sema, then codegen error *"Resource access is not guaranteed to map to a unique global resource"* | ✅ Codegen error: *"local resource not guaranteed to map to unique global resource"* |
| [`ternary_lvalue_unambiguous`] | Ternary lvalue with a statically constant condition (`(true ? a : b) = g`) | Warning † at sema (front end is syntactic and cannot prove unambiguity); Clean codegen (backend folds the constant condition) | Store targets the statically-selected side (`a` here) | ❌ Clean at sema (warning does not fire); ✅ Clean codegen | ✅ Clean |
| [`bindings_errs`] | Grouped warning cases: ternary initializer, reassignment from a resource-array element, ternary assignment to an uninitialized local, and ternary assignment to a `static` global | Warning † (each shape leaves the binding ambiguous) | N/A | ✅ Warning (`-Whlsl-explicit-binding`) for all four shapes | ❌ Clean (no diagnostic for any shape) |
| [`bindings`] | Grouped must-not-warn cases pinning the diagnostic's lower boundary: single-path conditional assign, self-assign of an uninitialized local, conditional reassign to the *same* global, and ternary/if-else selecting between elements of one resource array | Clean (binding stays unique in every shape) | Store reaches the single selected global | ✅ Clean | ✅ Clean |

### Global Resource Array Indexing

| Test | Behavior | Ought Compile | Ought Runtime | Clang | DXC |
|------|----------|---------------|---------------|-------|-----|
| [`init_from_global_array_dynamic_index`] | Initialize a local from a dynamically-indexed element of a global resource array | Clean | Store reaches the dynamically-indexed global | ✅ | ✅ |

### Static Storage

| Test | Behavior | Ought Compile | Ought Runtime | Clang | DXC |
|------|----------|---------------|---------------|-------|-----|
| [`static_local`] | `static RWByteAddressBuffer buf = g;` inside a function | Clean | Store reaches the global; the binding persists across calls | ❌ Clean at `-O0`; asserts at `-O1`+ in `GlobalOpt` ([#205169](https://github.com/llvm/llvm-project/issues/205169)) | ❌ ICE: `llvm::cast<X>()` argument of incompatible type |
| [`static_const`] | `static const` local resource with `Load` method call | Error † (`Load` not `const`-qualified) | N/A | ❌ Clean (no diagnostic) | ❌ ICE |

### Invalid Type Operations

| Test | Behavior | Ought Compile | Ought Runtime | Clang | DXC |
|------|----------|---------------|---------------|-------|-----|
| [`assign_wrong_type`] | Assign `RWStructuredBuffer` to `RWByteAddressBuffer` | Error (incompatible resource types) | N/A | ✅ Error: *"no viable overloaded '='"* | ✅ Error: type mismatch |

### Invalid Declarations

| Test | Behavior | Ought Compile | Ought Runtime | Clang | DXC |
|------|----------|---------------|---------------|-------|-----|
| [`explicit_register`] | Explicit `register()` attribute on a local resource variable | Error (`register` only applies to globals) | N/A | ✅ Error: *"'register' attribute only applies to cbuffer/tbuffer and external global variables"* | ❌ Clean (silently ignores the local `register()`) |

## Key Behavioral Themes

### Ambiguous Binding: Sema Warning vs. CodeGen Error

A recurring pattern across the tables above is a local resource whose
binding cannot be resolved to a single unique global at compile time
(reassignment across control flow, ternary merges, etc.). The expected
behavior is a compile-time diagnostic that surfaces the ambiguity to the
user. Clang emits
`-Whlsl-explicit-binding` at sema for these patterns. DXC has no
equivalent sema diagnostic — it either silently accepts the pattern
(producing implementation-defined runtime behavior) or rejects it as a
hard error during its `DxilCondenseResources` codegen pass. Neither
behavior is the spec-defined baseline; the ought-tables flag both
deviations.

### Both Compilers Crash on Static Resources

DXC asserts internally on `static` local resources and `static const`
resources. Clang accepts both at `-O0`, but a plain `static` local
resource also asserts in Clang once optimizations run
(`GlobalOpt`/`SRAGlobal` at `-O1` and above,
[#205169](https://github.com/llvm/llvm-project/issues/205169)). These
are compiler bugs in both, not intentional behavior.

### Texture2D vs RWByteAddressBuffer

Some behaviors differ between resource types. DXC ICEs with both
`static Texture2D` and `static RWByteAddressBuffer`. The test suite
uses `RWByteAddressBuffer` because Clang does not yet support `Texture2D`.

## Test Placement

Test placement follows from each row's "Ought Compile" column above, not
from which compiler currently passes or fails. Within the set of shaders
that ought to compile, placement further depends on whether the test
exercises behavior that benefits from on-hardware validation.

**Motivation.** Local resource assignment is, fundamentally, a static
question: which global resource does each use of a local handle bind to?
That question is answered entirely by tracking how a pointer to a global
flows through assignments, returns, parameters, struct members, and
control flow — all of which are visible in the LLVM IR. For the bulk of
the surface area covered by this proposal, a focused IR test in the
clang tree (`CodeGenHLSL/` for codegen, `SemaHLSL/` for diagnostics)
gives a sharper, faster, and more vendor-agnostic check than running a
compute shader on real hardware and comparing buffer contents. Running
every pattern on real GPUs would mostly be re-verifying the IR through a
much noisier and slower channel.

The offload test suite is reserved for cases where on-hardware behavior
adds information that IR inspection cannot — that is, where the
*execution* of the shader, not just its IR, is the interesting thing.

- Shaders that **ought to compile without error** (Clean or Warning)
  belong in the
  [offload test suite](https://github.com/llvm/offload-test-suite)
  under `test/Feature/LocalResources/` **only if** the test exercises
  one of:
  - a **common, idiomatic HLSL usage pattern** that a smoke test should
    catch end-to-end (initialization from a global, reassignment,
    function forwarding, struct member access, simple control flow); or
  - a pattern whose **runtime behavior may differ across vendors,
    drivers, or targets** (e.g. wave-conditional reassignment,
    bindless / unbounded resource arrays, group-shared interactions),
    where comparing actual GPU output is the only way to catch a
    divergence.

  Everything else that ought to compile — pattern variants whose
  binding resolution is fully decidable by reading the IR (e.g.
  static-condition ternaries that collapse to a single global, plain
  shadowing, no-op self-assignment, simple aliasing) — belongs as an
  IR-level test in the clang tree (`CodeGenHLSL/`) rather than as an
  offload test. Where a compiler's current behavior disagrees with the
  Ought column, prefer filing a tracking issue that carries the repro
  over landing a test that pins the wrong behavior. XFAIL is only useful
  when the expected output is already known exactly; for a diagnostic
  that does not exist yet, `-verify` fails on *unexpected* diagnostics
  too, so an XFAILed test whose guessed wording does not match stays
  silently XFAILed instead of signaling that it should be re-enabled.

- Shaders that **ought to fail compilation with an error** belong in
  the clang tree (typically `SemaHLSL/`), where `-verify` can pin the
  expected diagnostic. They are not added to the offload test suite
  regardless of any current compiler's behavior.

- Shaders whose Ought claim is **TBD / unspecified** are blocked on
  spec work; this document is the place to surface those gaps so the
  HLSL spec issues can be filed.

The net effect is that the offload `LocalResources/` directory holds a
small, curated set of shaders that together cover the everyday
patterns and the vendor-divergent ones; the long tail of variant
patterns lives as IR-level tests in clang, where they are easier to
maintain and faster to run.

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

Helena Kotas, Justin Bogner, Finn Plummer

<!-- godbolt-link-defs -->
[`consolidated_assignments`]: https://godbolt.org/clientstate/eyJzZXNzaW9ucyI6W3siaWQiOjEsImxhbmd1YWdlIjoiaGxzbCIsInNvdXJjZSI6IlJXQnl0ZUFkZHJlc3NCdWZmZXIgR0J1ZjAgOiByZWdpc3Rlcih1MCk7XG5SV0J5dGVBZGRyZXNzQnVmZmVyIEdCdWYxIDogcmVnaXN0ZXIodTEpO1xuXG5zdHJ1Y3QgUmVzSG9sZGVyIHtcbiAgICBSV0J5dGVBZGRyZXNzQnVmZmVyIEJ1ZjtcbiAgICB1aW50IFZhbHVlO1xufTtcblxuUldCeXRlQWRkcmVzc0J1ZmZlciBHZXRCdWYoKSB7XG4gICAgUldCeXRlQWRkcmVzc0J1ZmZlciBMb2NhbCA9IEdCdWYwO1xuICAgIHJldHVybiBMb2NhbDtcbn1cblxudm9pZCBEb1N0b3JlKGlub3V0IFJXQnl0ZUFkZHJlc3NCdWZmZXIgQnVmLCB1aW50IElkeCkge1xuICAgIEJ1Zi5TdG9yZShJZHgsIDQyKTtcbn1cbnZvaWQgRm9yd2FyZFN0b3JlKFJXQnl0ZUFkZHJlc3NCdWZmZXIgQnVmLCB1aW50IElkeCkge1xuICAgIERvU3RvcmUoQnVmLCBJZHgpO1xufVxuXG52b2lkIFdyaXRlVGhyb3VnaChvdXQgUldCeXRlQWRkcmVzc0J1ZmZlciBCdWYpIHtcbiAgICBCdWYgPSBHQnVmMDtcbn1cblxuW251bXRocmVhZHMoMSwxLDEpXVxudm9pZCBtYWluKHVpbnQgR0kgOiBTVl9Hcm91cEluZGV4KSB7XG5cbiAgUmVzSG9sZGVyIEggPSB7R2V0QnVmKCksIDB9O1xuICBSV0J5dGVBZGRyZXNzQnVmZmVyIEJ1ZiA9ICh0cnVlID8gSC5CdWYgOiBHQnVmMSk7XG4gIGlmIChmYWxzZSlcbiAgICBCdWYgPSBHQnVmMTtcbiAgaWYgKHRydWUpXG4gICAgQnVmID0gQnVmO1xuICBSV0J5dGVBZGRyZXNzQnVmZmVyIEFsaWFzID0gQnVmO1xuICBSV0J5dGVBZGRyZXNzQnVmZmVyIENvbW1hID0gKEdCdWYxLCBBbGlhcyk7XG5cbiAgRm9yd2FyZFN0b3JlKENvbW1hLCAwKTtcblxuICBHZXRCdWYoKS5TdG9yZSg0LCA0Mik7XG5cbiAgUldCeXRlQWRkcmVzc0J1ZmZlciBGcm9tUmV0ID0gR2V0QnVmKCk7XG4gIEZyb21SZXQuU3RvcmUoOCwgNDIpO1xuXG4gIFJXQnl0ZUFkZHJlc3NCdWZmZXIgQm90aFNhbWUgPSAoR0kgIT0gMCkgPyBHQnVmMCA6IEdCdWYwO1xuICBCb3RoU2FtZS5TdG9yZSgxMiwgNDIpO1xuXG4gIFJXQnl0ZUFkZHJlc3NCdWZmZXIgRnJvbU91dDtcbiAgV3JpdGVUaHJvdWdoKEZyb21PdXQpO1xuICBGcm9tT3V0LlN0b3JlKDE2LCA0Mik7XG5cbiAgUmVzSG9sZGVyIE1peGVkO1xuICBNaXhlZC5CdWYgPSBHQnVmMDtcbiAgTWl4ZWQuVmFsdWUgPSA0MjtcbiAgTWl4ZWQuQnVmLlN0b3JlKDIwLCBNaXhlZC5WYWx1ZSk7XG59XG4iLCJjb21waWxlcnMiOlt7ImlkIjoiZHhjX3RydW5rIiwib3B0aW9ucyI6Ii1UIGNzXzZfMyAtRSBtYWluIiwibGlicyI6W10sInRvb2xzIjpbXX0seyJpZCI6Imhsc2xfY2xhbmdfdHJ1bmsiLCJvcHRpb25zIjoiLVQgY3NfNl8zIC1FIG1haW4iLCJsaWJzIjpbXSwidG9vbHMiOltdfV19XX0%3D
[`array`]: https://godbolt.org/clientstate/eyJzZXNzaW9ucyI6W3siaWQiOjEsImxhbmd1YWdlIjoiaGxzbCIsInNvdXJjZSI6IlJXQnl0ZUFkZHJlc3NCdWZmZXIgT3V0IDogcmVnaXN0ZXIodTApO1xuUldCeXRlQWRkcmVzc0J1ZmZlciBBdXggOiByZWdpc3Rlcih1MSk7XG5cbltudW10aHJlYWRzKDEsMSwxKV1cbnZvaWQgbWFpbigpIHtcbiAgICBSV0J5dGVBZGRyZXNzQnVmZmVyIEFyclsyXTtcbiAgICBSV0J5dGVBZGRyZXNzQnVmZmVyIEFycjJbMV07XG4gICAgQXJyWzBdID0gT3V0O1xuICAgIEFycjJbMF0gPSBBdXg7XG4gICAgQXJyWzBdLlN0b3JlKDAsIDQyKTtcbiAgICBBcnIyWzBdLlN0b3JlKDQsIDk5KTtcbn1cbiIsImNvbXBpbGVycyI6W3siaWQiOiJkeGNfdHJ1bmsiLCJvcHRpb25zIjoiLVQgY3NfNl8zIC1FIG1haW4iLCJsaWJzIjpbXSwidG9vbHMiOltdfSx7ImlkIjoiaGxzbF9jbGFuZ190cnVuayIsIm9wdGlvbnMiOiItVCBjc182XzMgLUUgbWFpbiIsImxpYnMiOltdLCJ0b29scyI6W119XX1dfQ%3D%3D
[`array_partial_init_dynamic`]: https://godbolt.org/clientstate/eyJzZXNzaW9ucyI6W3siaWQiOjEsImxhbmd1YWdlIjoiaGxzbCIsInNvdXJjZSI6IlJXQnl0ZUFkZHJlc3NCdWZmZXIgT3V0IDogcmVnaXN0ZXIodTApO1xuXG5bbnVtdGhyZWFkcygxLDEsMSldXG52b2lkIG1haW4odWludDMgVGlkIDogU1ZfRGlzcGF0Y2hUaHJlYWRJRCkge1xuICAgIFJXQnl0ZUFkZHJlc3NCdWZmZXIgQXJyWzRdO1xuICAgIEFyclswXSA9IE91dDtcbiAgICBBcnJbMV0gPSBPdXQ7XG4gICAgQXJyW1RpZC54ICYgMV0uU3RvcmUoMCwgNDIpO1xufVxuIiwiY29tcGlsZXJzIjpbeyJpZCI6ImR4Y190cnVuayIsIm9wdGlvbnMiOiItVCBjc182XzMgLUUgbWFpbiIsImxpYnMiOltdLCJ0b29scyI6W119LHsiaWQiOiJobHNsX2NsYW5nX3RydW5rIiwib3B0aW9ucyI6Ii1UIGNzXzZfMyAtRSBtYWluIiwibGlicyI6W10sInRvb2xzIjpbXX1dfV19
[`assign_wrong_type`]: https://godbolt.org/clientstate/eyJzZXNzaW9ucyI6W3siaWQiOjEsImxhbmd1YWdlIjoiaGxzbCIsInNvdXJjZSI6IlJXQnl0ZUFkZHJlc3NCdWZmZXIgR0J1ZjAgOiByZWdpc3Rlcih1MCk7XG5SV1N0cnVjdHVyZWRCdWZmZXI8dWludD4gR1NCIDogcmVnaXN0ZXIodTEpO1xuXG5bbnVtdGhyZWFkcygxLDEsMSldXG52b2lkIG1haW4odWludDMgVGlkIDogU1ZfRGlzcGF0Y2hUaHJlYWRJRCkge1xuICAgIFJXQnl0ZUFkZHJlc3NCdWZmZXIgQnVmID0gR0J1ZjA7XG4gICAgUldTdHJ1Y3R1cmVkQnVmZmVyPHVpbnQ%2BIFNiID0gR1NCO1xuICAgIEJ1ZiA9IFNiO1xufVxuIiwiY29tcGlsZXJzIjpbeyJpZCI6ImR4Y190cnVuayIsIm9wdGlvbnMiOiItVCBjc182XzMgLUUgbWFpbiIsImxpYnMiOltdLCJ0b29scyI6W119LHsiaWQiOiJobHNsX2NsYW5nX3RydW5rIiwib3B0aW9ucyI6Ii1UIGNzXzZfMyAtRSBtYWluIiwibGlicyI6W10sInRvb2xzIjpbXX1dfV19
[`const_local_store`]: https://godbolt.org/clientstate/eyJzZXNzaW9ucyI6W3siaWQiOjEsImxhbmd1YWdlIjoiaGxzbCIsInNvdXJjZSI6IlJXQnl0ZUFkZHJlc3NCdWZmZXIgR0J1ZiA6IHJlZ2lzdGVyKHUwKTtcblxudWludCBMb2FkQ29uc3QoY29uc3QgUldCeXRlQWRkcmVzc0J1ZmZlciBCdWYpIHtcbiAgICByZXR1cm4gQnVmLkxvYWQoMCk7XG59XG5cbltudW10aHJlYWRzKDEsMSwxKV1cbnZvaWQgbWFpbigpIHtcbiAgICBjb25zdCBSV0J5dGVBZGRyZXNzQnVmZmVyIExvY2FsID0gR0J1ZjtcbiAgICB1aW50IFZhbCA9IExvYWRDb25zdChMb2NhbCk7XG4gICAgTG9jYWwuU3RvcmUoMCwgVmFsKTtcbn1cbiIsImNvbXBpbGVycyI6W3siaWQiOiJkeGNfdHJ1bmsiLCJvcHRpb25zIjoiLVQgY3NfNl8zIC1FIG1haW4iLCJsaWJzIjpbXSwidG9vbHMiOltdfSx7ImlkIjoiaGxzbF9jbGFuZ190cnVuayIsIm9wdGlvbnMiOiItVCBjc182XzMgLUUgbWFpbiIsImxpYnMiOltdLCJ0b29scyI6W119XX1dfQ%3D%3D
[`explicit_register`]: https://godbolt.org/clientstate/eyJzZXNzaW9ucyI6W3siaWQiOjEsImxhbmd1YWdlIjoiaGxzbCIsInNvdXJjZSI6IlJXQnl0ZUFkZHJlc3NCdWZmZXIgRzAgOiByZWdpc3Rlcih1MCk7XG5cbltudW10aHJlYWRzKDEsMSwxKV1cbnZvaWQgbWFpbih1aW50MyBUaWQgOiBTVl9EaXNwYXRjaFRocmVhZElEKVxue1xuICAgIFJXQnl0ZUFkZHJlc3NCdWZmZXIgQnVmIDogcmVnaXN0ZXIodTUpID0gRzA7XG4gICAgQnVmLlN0b3JlKFRpZC54ICogNCwgNDIpO1xufVxuIiwiY29tcGlsZXJzIjpbeyJpZCI6ImR4Y190cnVuayIsIm9wdGlvbnMiOiItVCBjc182XzMgLUUgbWFpbiIsImxpYnMiOltdLCJ0b29scyI6W119LHsiaWQiOiJobHNsX2NsYW5nX3RydW5rIiwib3B0aW9ucyI6Ii1UIGNzXzZfMyAtRSBtYWluIiwibGlicyI6W10sInRvb2xzIjpbXX1dfV19
[`init_from_global_array_dynamic_index`]: https://godbolt.org/clientstate/eyJzZXNzaW9ucyI6W3siaWQiOjEsImxhbmd1YWdlIjoiaGxzbCIsInNvdXJjZSI6IlJXQnl0ZUFkZHJlc3NCdWZmZXIgR0J1ZkFycmF5WzRdIDogcmVnaXN0ZXIodTApO1xuXG5bbnVtdGhyZWFkcygxLDEsMSldXG52b2lkIG1haW4odWludDMgVGlkIDogU1ZfRGlzcGF0Y2hUaHJlYWRJRCkge1xuICAgIFJXQnl0ZUFkZHJlc3NCdWZmZXIgQnVmID0gR0J1ZkFycmF5W1RpZC54ICYgM107XG4gICAgQnVmLlN0b3JlKDAsIDQyKTtcbn1cbiIsImNvbXBpbGVycyI6W3siaWQiOiJkeGNfdHJ1bmsiLCJvcHRpb25zIjoiLVQgY3NfNl8zIC1FIG1haW4iLCJsaWJzIjpbXSwidG9vbHMiOltdfSx7ImlkIjoiaGxzbF9jbGFuZ190cnVuayIsIm9wdGlvbnMiOiItVCBjc182XzMgLUUgbWFpbiIsImxpYnMiOltdLCJ0b29scyI6W119XX1dfQ%3D%3D
[`branched_reassign_ambiguous`]: https://godbolt.org/clientstate/eyJzZXNzaW9ucyI6W3siaWQiOjEsImxhbmd1YWdlIjoiaGxzbCIsInNvdXJjZSI6IlJXQnl0ZUFkZHJlc3NCdWZmZXIgR0J1ZjEgOiByZWdpc3Rlcih1MSk7XG5SV0J5dGVBZGRyZXNzQnVmZmVyIEdCdWYyIDogcmVnaXN0ZXIodTIpO1xuXG52b2lkIFBhc3NfQnJhbmNoZWRSZWFzc2lnbih1aW50IENvbmQsIHVpbnQgSWR4KSB7XG4gICAgUldCeXRlQWRkcmVzc0J1ZmZlciBCdWYgPSBHQnVmMTtcbiAgICBpZiAoQ29uZCkge1xuICAgICAgICBCdWYgPSBHQnVmMjtcbiAgICB9XG4gICAgQnVmLlN0b3JlKElkeCAqIDQsIDMyKTtcbn1cblxuW251bXRocmVhZHMoOCw4LDEpXVxudm9pZCBtYWluKHVpbnQzIFRpZCA6IFNWX0Rpc3BhdGNoVGhyZWFkSUQpIHtcbiAgICB1aW50IElkeCA9IFRpZC54ICsgVGlkLnkgKiA4O1xuICAgIFBhc3NfQnJhbmNoZWRSZWFzc2lnbihUaWQueCAmIDEsIElkeCk7XG59XG4iLCJjb21waWxlcnMiOlt7ImlkIjoiZHhjX3RydW5rIiwib3B0aW9ucyI6Ii1UIGNzXzZfMyAtRSBtYWluIiwibGlicyI6W10sInRvb2xzIjpbXX0seyJpZCI6Imhsc2xfY2xhbmdfdHJ1bmsiLCJvcHRpb25zIjoiLVQgY3NfNl8zIC1FIG1haW4iLCJsaWJzIjpbXSwidG9vbHMiOltdfV19XX0%3D
[`static_const`]: https://godbolt.org/clientstate/eyJzZXNzaW9ucyI6W3siaWQiOjEsImxhbmd1YWdlIjoiaGxzbCIsInNvdXJjZSI6IlJXQnl0ZUFkZHJlc3NCdWZmZXIgR0J1ZjAgOiByZWdpc3Rlcih1MCk7XG5cbnZvaWQgRmFpbF9TdGF0aWNDb25zdCh1aW50IElkeCkge1xuICAgIHN0YXRpYyBjb25zdCBSV0J5dGVBZGRyZXNzQnVmZmVyIEJ1ZiA9IEdCdWYwO1xuICAgIEJ1Zi5Mb2FkKElkeCAqIDQpO1xufVxuXG5bbnVtdGhyZWFkcygxLDEsMSldXG52b2lkIG1haW4odWludDMgVGlkIDogU1ZfRGlzcGF0Y2hUaHJlYWRJRCkge1xuICAgIEZhaWxfU3RhdGljQ29uc3QoVGlkLngpO1xufVxuIiwiY29tcGlsZXJzIjpbeyJpZCI6ImR4Y190cnVuayIsIm9wdGlvbnMiOiItVCBjc182XzMgLUUgbWFpbiIsImxpYnMiOltdLCJ0b29scyI6W119LHsiaWQiOiJobHNsX2NsYW5nX3RydW5rIiwib3B0aW9ucyI6Ii1UIGNzXzZfMyAtRSBtYWluIiwibGlicyI6W10sInRvb2xzIjpbXX1dfV19
[`static_local`]: https://godbolt.org/clientstate/eyJzZXNzaW9ucyI6W3siaWQiOjEsImxhbmd1YWdlIjoiaGxzbCIsInNvdXJjZSI6IlJXQnl0ZUFkZHJlc3NCdWZmZXIgR0J1ZjAgOiByZWdpc3Rlcih1MCk7XG5cbnZvaWQgUGFzc19TdGF0aWNMb2NhbCh1aW50IElkeCkge1xuICAgIHN0YXRpYyBSV0J5dGVBZGRyZXNzQnVmZmVyIEJ1ZiA9IEdCdWYwO1xuICAgIEJ1Zi5TdG9yZShJZHggKiA0LCAxKTtcbn1cblxuW251bXRocmVhZHMoMSwxLDEpXVxudm9pZCBtYWluKHVpbnQzIFRpZCA6IFNWX0Rpc3BhdGNoVGhyZWFkSUQpIHtcbiAgICBQYXNzX1N0YXRpY0xvY2FsKFRpZC54KTtcbn1cbiIsImNvbXBpbGVycyI6W3siaWQiOiJkeGNfdHJ1bmsiLCJvcHRpb25zIjoiLVQgY3NfNl8zIC1FIG1haW4iLCJsaWJzIjpbXSwidG9vbHMiOltdfSx7ImlkIjoiaGxzbF9jbGFuZ190cnVuayIsIm9wdGlvbnMiOiItVCBjc182XzMgLUUgbWFpbiIsImxpYnMiOltdLCJ0b29scyI6W119XX1dfQ%3D%3D
[`ternary_lvalue_unambiguous`]: https://godbolt.org/clientstate/eyJzZXNzaW9ucyI6W3siaWQiOjEsImxhbmd1YWdlIjoiaGxzbCIsInNvdXJjZSI6IlJXQnl0ZUFkZHJlc3NCdWZmZXIgR0J1ZjAgOiByZWdpc3Rlcih1MCk7XG5SV0J5dGVBZGRyZXNzQnVmZmVyIEdCdWYxIDogcmVnaXN0ZXIodTEpO1xuXG5bbnVtdGhyZWFkcygxLDEsMSldXG52b2lkIG1haW4odWludDMgVGlkIDogU1ZfRGlzcGF0Y2hUaHJlYWRJRCkge1xuICAgIFJXQnl0ZUFkZHJlc3NCdWZmZXIgQSA9IEdCdWYwO1xuICAgIFJXQnl0ZUFkZHJlc3NCdWZmZXIgQiA9IEdCdWYxO1xuICAgICh0cnVlID8gQSA6IEIpID0gR0J1ZjA7XG4gICAgQS5TdG9yZShUaWQueCAqIDQsIDEpO1xuICAgIEIuU3RvcmUoVGlkLnggKiA0LCAyKTtcbn1cbiIsImNvbXBpbGVycyI6W3siaWQiOiJkeGNfdHJ1bmsiLCJvcHRpb25zIjoiLVQgY3NfNl8zIC1FIG1haW4iLCJsaWJzIjpbXSwidG9vbHMiOltdfSx7ImlkIjoiaGxzbF9jbGFuZ190cnVuayIsIm9wdGlvbnMiOiItVCBjc182XzMgLUUgbWFpbiIsImxpYnMiOltdLCJ0b29scyI6W119XX1dfQ%3D%3D
[`bindings_errs`]: https://godbolt.org/clientstate/eyJzZXNzaW9ucyI6W3siaWQiOjEsImxhbmd1YWdlIjoiaGxzbCIsInNvdXJjZSI6IlJXQnVmZmVyPHVpbnQ%2BIEluIDogcmVnaXN0ZXIodTApO1xuUldTdHJ1Y3R1cmVkQnVmZmVyPHVpbnQ%2BIE91dDAgOiByZWdpc3Rlcih1MSk7XG5SV1N0cnVjdHVyZWRCdWZmZXI8dWludD4gT3V0MSA6IHJlZ2lzdGVyKHUyKTtcblJXU3RydWN0dXJlZEJ1ZmZlcjx1aW50PiBPdXRBcnJbXTtcblxuY2J1ZmZlciBjIHtcbiAgICBib29sIGNvbmQ7XG59O1xuXG52b2lkIGNvbmRpdGlvbmFsX2luaXRpYWxpemF0aW9uKHVpbnQgaWR4KSB7XG4gICAgUldTdHJ1Y3R1cmVkQnVmZmVyPHVpbnQ%2BIE91dCA9IGNvbmQgPyBPdXQwIDogT3V0MTtcbiAgICBPdXRbaWR4XSA9IEluW2lkeF07XG59XG5cbnZvaWQgYnJhbmNoZWRfYXNzaWdubWVudF93aXRoX2FycmF5KHVpbnQgaWR4KSB7XG4gICAgUldTdHJ1Y3R1cmVkQnVmZmVyPHVpbnQ%2BIE91dCA9IE91dDA7IC8vIGV4cGVjdGVkLW5vdGUge3t2YXJpYWJsZSAnT3V0JyBpcyBkZWNsYXJlZCBoZXJlfX1cbiAgICBpZiAoY29uZCkge1xuICAgICAgICBPdXQgPSBPdXRBcnJbMF07XG4gICAgfVxuICAgIE91dFtpZHhdID0gSW5baWR4XTtcbn1cblxudm9pZCBjb25kaXRpb25hbF9hc3NpZ25tZW50KHVpbnQgaWR4KSB7XG4gICAgUldTdHJ1Y3R1cmVkQnVmZmVyPHVpbnQ%2BIE91dDtcbiAgICBPdXQgPSBjb25kID8gT3V0MCA6IE91dDE7XG4gICAgT3V0W2lkeF0gPSBJbltpZHhdO1xufVxuXG5zdGF0aWMgUldTdHJ1Y3R1cmVkQnVmZmVyPHVpbnQ%2BIFN0YXRpY091dDtcblxudm9pZCBzdGF0aWNfY29uZGl0aW9uYWxfYXNzaWdubWVudCh1aW50IGlkeCkge1xuICAgIFN0YXRpY091dCA9IGNvbmQgPyBPdXQwIDogT3V0MTtcbiAgICBTdGF0aWNPdXRbaWR4XSA9IEluW2lkeF07XG59XG4iLCJjb21waWxlcnMiOlt7ImlkIjoiZHhjX3RydW5rIiwib3B0aW9ucyI6Ii1UIGxpYl82XzYiLCJsaWJzIjpbXSwidG9vbHMiOltdfSx7ImlkIjoiaGxzbF9jbGFuZ190cnVuayIsIm9wdGlvbnMiOiItVCBsaWJfNl82IiwibGlicyI6W10sInRvb2xzIjpbXX1dfV19
[`bindings`]: https://godbolt.org/clientstate/eyJzZXNzaW9ucyI6W3siaWQiOjEsImxhbmd1YWdlIjoiaGxzbCIsInNvdXJjZSI6IlJXQnVmZmVyPHVpbnQ%2BIEluIDogcmVnaXN0ZXIodTApO1xuUldTdHJ1Y3R1cmVkQnVmZmVyPHVpbnQ%2BIE91dDAgOiByZWdpc3Rlcih1MSk7XG5SV1N0cnVjdHVyZWRCdWZmZXI8dWludD4gT3V0MSA6IHJlZ2lzdGVyKHUyKTtcblJXU3RydWN0dXJlZEJ1ZmZlcjx1aW50PiBPdXRBcnJbXTtcblxuY2J1ZmZlciBjIHtcbiAgICBib29sIGNvbmQ7XG59O1xuXG52b2lkIHNhbWVfYXNzaWdubWVudCh1aW50IGlkeCkge1xuICAgIFJXU3RydWN0dXJlZEJ1ZmZlcjx1aW50PiBPdXQgPSBPdXQxO1xuICAgIGlmIChjb25kKSB7XG4gICAgICAgIE91dCA9IE91dDE7XG4gICAgfVxuICAgIE91dFtpZHhdID0gSW5baWR4XTtcbn1cblxudm9pZCBjb25kaXRpb25hbF9pbml0aWFsaXphdGlvbl93aXRoX2luZGV4KHVpbnQgaWR4KSB7XG4gICAgUldTdHJ1Y3R1cmVkQnVmZmVyPHVpbnQ%2BIE91dCA9IGNvbmQgPyBPdXRBcnJbMF0gOiBPdXRBcnJbMV07XG4gICAgT3V0W2lkeF0gPSBJbltpZHhdO1xufVxuXG52b2lkIGNvbmRpdGlvbmFsX2Fzc2lnbm1lbnRfd2l0aF9pbmRleCh1aW50IGlkeCkge1xuICAgIFJXU3RydWN0dXJlZEJ1ZmZlcjx1aW50PiBPdXQ7XG5cdGlmIChjb25kKSB7XG5cdFx0T3V0ID0gT3V0QXJyWzBdO1xuXHR9IGVsc2Uge1xuXHRcdE91dCA9IE91dEFyclsxXTtcblx0fVxuICAgIE91dFtpZHhdID0gSW5baWR4XTtcbn1cblxudm9pZCByZWFzc2lnbm1lbnQodWludCBpZHgpIHtcbiAgICBSV1N0cnVjdHVyZWRCdWZmZXI8dWludD4gT3V0ID0gT3V0MDtcblx0aWYgKGNvbmQpIHtcblx0XHRPdXQgPSBPdXQwO1xuXHR9XG5cdE91dFtpZHhdID0gSW5baWR4XTtcbn1cblxudm9pZCBjb25kaXRpb25hbF9yZXN1bHRfaW5fc2FtZSh1aW50IGlkeCkge1xuICAgIFJXU3RydWN0dXJlZEJ1ZmZlcjx1aW50PiBPdXQgPSBjb25kID8gT3V0MCA6IE91dDA7XG5cdE91dFtpZHhdID0gSW5baWR4XTtcbn1cbiIsImNvbXBpbGVycyI6W3siaWQiOiJkeGNfdHJ1bmsiLCJvcHRpb25zIjoiLVQgbGliXzZfNiIsImxpYnMiOltdLCJ0b29scyI6W119LHsiaWQiOiJobHNsX2NsYW5nX3RydW5rIiwib3B0aW9ucyI6Ii1UIGxpYl82XzYiLCJsaWJzIjpbXSwidG9vbHMiOltdfV19XX0%3D
<!-- /godbolt-link-defs -->
