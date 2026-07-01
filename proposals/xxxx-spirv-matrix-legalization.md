---
title: "[xxxx] - Legalize HLSL Matrix types to a chain of vectors for SPIR-V shader targets"
params:
  status: Under Consideration
  authors:
    - farzonl: Farzon Lotfi
---

## Introduction

HLSL matrix types flatten to wide `<N x T>` vectors (e.g. `bool3x4` → `<12 x i1>`),
but SPIR-V shader/Vulkan targets cap vectors at 4 components. The GlobalISel
legalizer must split wide loads, stores, extends, and shuffles into legal chunks.
See https://github.com/llvm/llvm-project/issues/186864.

## Background

Today a a vector of size 6. is expanded to 8, and then split. This can cause
cascading problems when legalizing other Global opcodes And forces per opcode 
legalizations, which will be an ongoing cost as new opcodes are supported in
the SPIR-V backend. It would be better if we did not do things to actively
build illigal vector sizes in the first place.

## Requirements

- Never materialize a SPIR-V vector wider than 4 components on shader targets.
- Emitted SPIR-V must pass `spirv-val`; no correctness regressions in the suite.
- Preserve vectorization where it is beneficial instead of scalarizing everything.

## Motivation

Transpose/multiply of a flattened matrix produces a wide `G_SHUFFLE_VECTOR` that
cannot be represented directly. A naive split either crashes selection or
scalarizes it into per-element extract/insert, producing far worse codegen than
the vector `OpVectorShuffle`/`OpDot`/`OpSelect` a shader consumer can use.

## Options

Three strategies were evaluated for the wide `G_SHUFFLE_VECTOR`:

### Option A — Always scalarize (`LegalizerHelper::lowerShuffleVector`)

Lower every wide shuffle generically to `G_EXTRACT_VECTOR_ELT` + `G_BUILD_VECTOR`.

- Pros: width-agnostic, always correct, needs no power-of-two padding.
- Cons: emits one extract/construct per element even when the result feeds a
  vector consumer (`OpDot` in matrix-multiply, `OpSelect` in bool transpose).
  The `OpVectorShuffle`s that a shader can execute in one instruction are lost,
  so matrix-multiply and bool-transpose regress to fully scalar code.

### Option B — Pad to the next power of two, then split to 4-lane chunks

Use `moreElementsToNextPow2` then `fewerElementsIf(... MaxVectorSize)`.

- Pros: reuses existing generic split actions; uniform 4-lane chunks.
- Cons: padding `<12>`→`<16>`, `<6>`→`<8>`, `<9>`→`<16>` forces an illegal
  wide `G_BUILD_VECTOR` with undef lanes, and the padded widths incidentally
  match the internal load-gather shuffles, breaking
  `pointers/load-vector-from-array-of-vectors.ll`. Padding also wastes lanes and
  adds undef bookkeeping the backend must then clean up.
- This is essentially what we were already doing and it was easy for it to fall
  on its face.

### Option C — Split into the largest common divisor chunk width (chosen)

Split both operands into `W`-lane chunks, where `W` is the largest divisor of the
element count in `[2, MaxVectorSize]` shared by source and destination
(`<12>`→3×`<4>`, `<6>`→2×`<3>`, `<9>`→3×`<3>`), and emit chained per-chunk
`OpVectorShuffle`s. This keeps every chunk a legal SPIR-V vector with no undef
padding and preserves vectorized `OpDot`/`OpSelect` downstream.

**Why C:** it is the only option that satisfies all requirements at once —
legal chunk widths with no padding artifacts (unlike B), and preserved
vectorization for real vector consumers (unlike A). It is paired with a
use-aware guard so it only fires when vectorization actually helps.

## Implementation

Option C is implemented in in my llvm-project PR on `SPIRVLegalizerInfo.cpp`:

1. **Chunk-width selection** — `getVectorSplitWidth(NumElts, MaxVectorSize, IsShader)`
   returns, for shader targets, the largest divisor of `NumElts`.
2. **Type-only gate** — the `ShuffleChunkable` predicate feeds
   `G_SHUFFLE_VECTOR`'s `.customIf(...)`. It requires a shader target, vector
   source and destination both wider than `MaxVectorSize`, and equal, `>= 2`
   split widths for source and destination. It **excludes power-of-two element
   counts**, because load legalization emits an internal `<5>`/`<8>` gather
   shuffle whose padded form would otherwise match and break the pointer
   load-vector test.

3. **Custom lowering** — `legalizeShuffleVector` splits each source into `W`-lane
   chunks and builds each destination chunk with chained `OpVectorShuffle`s,
   then concatenates the result. Chunkable cases that do not apply fall through
   to `moreElementsToNextPow2` + `lowerIf(vectorElementCountIsGreaterThan)`.

4. **Use-aware opt-out** — before chunking, `legalizeShuffleVector` inspects the
   result's uses. If the shuffle feeds only a scatter store (a `G_STORE`, or a
   scalar `G_UNMERGE_VALUES` whose scalar defs are *not* recombined into a
   `G_BUILD_VECTOR`/`G_BUILD_VECTOR_TRUNC`), it falls back to the generic scalar
   lowering (`Helper.lower`), since the `OpVectorShuffle`s would immediately be
   undone by `OpCompositeExtract`s. When a def is recombined into a build-vector
   (matrix-multiply rebuilding `<3>` rows for `OpDot`) or feeds a vector extend
   (bool transpose `G_ZEXT`), the shuffle stays vectorized. This detection lives
   in the custom handler rather than the predicate because `customIf`'s
   `LegalityQuery` cannot see instruction uses, and because store legalization
   runs first (so "used only by stores" is unreliable — the stable KEEP signal
   is recombination into a build-vector).

5. **Post-legalizer type fix** — `SPIRVPostLegalizer.cpp`'s
   `deduceIntTypeFromResult` now preserves vector-ness so a split `<4 x i1>`
   trunc chunk gets a vector bool type (`OpINotEqual %v4bool`) rather than an
   invalid scalar bool.

## Conclusion

Validated with `spirv-val` and the full SPIR-V suite (1097 tests). Net result:
transpose (pure scatter-store) scalarizes cleanly, while matrix-multiply 
(`OpDot`) and bool transpose (`OpSelect`) stay vectorized.
