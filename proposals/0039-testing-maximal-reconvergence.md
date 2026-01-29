---
title: "0039 - Testing Maximal Reconvergence"
- draft: true
params:
  authors:
    - luciechoi: Lucie Choi
  sponsors:
    - s-perron: Steven Perron
    - Keenuts: Nathan Gauër
  status: Under Consideration
---

* PRs: [Testing in offload-test-suite
  (Draft)](https://github.com/llvm/offload-test-suite/pull/685)
* Issues: [Implementation in
  Clang](https://github.com/llvm/llvm-project/issues/136930)

## Introduction

This proposal seeks to add comprehensive conformance tests that HLSL compilers
(DXC and Clang) do not violate the optimization restrictions in section [1.6.3
of the HLSL
specification](https://microsoft.github.io/hlsl-specs/specs/hlsl.pdf?#page=9).

## Motivation

Graphics compilers often perform aggressive optimizations that can unexpectedly
alter the state of a thread in a wave. This is a critical issue for shaders
containing operations dependent on which threads are active, such as wave
intrinsics, as invalid transformations can lead to wrong or indeterminate
results. Historically, there is only an [informal
definition](https://github.com/microsoft/directxshadercompiler/wiki/wave-intrinsics#operation)
of which threads should be active at any point in execution of the shader:
"<i>implementations must enforce that the number of active lanes exactly
corresponds to the programmer’s view of flow control</i>". 

When lowering HLSL to SPIR-V, we must make sure the output matches this
expectation. To do so, there are 2 areas that need to be looked at:

#### 1. Adding `SPV_KHR_maximal_reconvergence` extension and `MaximallyReconvergesKHR` capability.

This is an indicator for the driver compilers to respect the above requirement
downstream. The frontend compilers will append these instructions if the
`-fspv-enable-maximal-reconvergence` flag is set.

#### 2. Ensuring the frontend compilers themselves do not alter the state during optimizations.

This is the place that needs extensive testing. In the below example, a compiler
may reorder the code (e.g loop unswitch pass) so that statements are moved
inside the branches, producing incorrect results.

| Before Optmization | After Optimization |
| --- | --- |
| <pre><code>if (non_uniform_cond) {<br>   doA(); <br>} else {<br>   doB(); <br>}<br>// Expected converged. <br>Out[...] = waveOperations(); </code></pre>| <pre><code>if (non_uniform_cond) {<br>   doA(); <br>   // Invalid transformation <br>   Out[...] = waveOperations();<br>} else {<br>   doB(); <br>   // Invalid transformation <br>   Out[...] = waveOperations(); <br>}<br></code></pre> |

This kind of optimization should be prevented, and in DXC, SPIR-V is used for
optimizing, so the instructions such as  `OpSelectionMerge` and `OpLoopMerge`
explicitly indicate a merge point and help avoid those control flow
modifications.

In Clang, we leverage [control convergence
tokens](https://llvm.org/docs/ConvergentOperations.html#overview) within the IR,
to explicitly mark the convergent operations (i.e. waves) and the convergence
points of the threads executing those instructions, so that optimization passes
can be aware and avoid invalid transformations.

Testing for correct convergence behavior is critical for reliability. Currently,
only a few unit tests exist. We need to extend this coverage to include complex
and highly divergent cases.

## Proposed solution

We propose implementing a comprehensive test suite in the offload-test-suite
repository that mirrors the logic of the Vulkan Conformance Testing Suite
(Vulkan-CTS). This involves generating shaders with random control flows (mixes
of if/switch statements, loops, and nesting) and verifying the results.

### Shader Generation

Approximately _N_ number of  HLSL shaders will be generated. These shaders use
fixed input buffers and write results to output buffers, where randomness is
derived from branching logic.

### CPU Simulation

A CPU simulation will track active thread indices and calculate the expected
result of wave operations based on specific subgroup sizes.


### Verification

We will generate a set of yaml test files for the offload-test-suite. For each
shader and subgroup size (4, 8, 16, 32), a test file will be generated that
executes the shader and verifies that the results match the CPU simulation.

## Detailed design

[This](https://github.com/llvm/offload-test-suite/pull/685) is an example of the
proposed design.

### Test Generation and Simulation

Since each GPU has different subgroup sizes, each machine will have a version
for every power-of-2 wave size between 4 and 32 (e.g., 4, 8, 16, 32). The tests
that do not match the subgroup size of the running GPU will be skipped (e.g.
through `# UNSUPPORTED: !SubgroupSizeX` directive).

### Translation

Logic from [Vulkan CTS GLSL
generation](https://github.com/KhronosGroup/VK-GL-CTS/blob/main/external/vulkancts/modules/vulkan/reconvergence/vktReconvergenceTests.cpp)
will be ported to produce HLSL. This includes translating intrinsics such as
`subgroupElect()` to `WaveIsFirstLane()` and `subgroupBallot()` to
`WaveActiveBallot()`, etc.

### Execution Pipeline

Only the code for the **random test generator** will reside in the
offload-test-suite repository. The shaders will be generated as part of the
pipeline. 

New steps will be added to the existing workflow at the end.

- Build DXC
- Build LLVM
- Dump GPU Info
- Run HLSL Tests
- **Generate Random Reconvergence Tests**
- **Run Reconvergence Tests**

This way, the execution of existing HLSL tests and the reconvergence tests are
separated.

```yaml
# .github/workflows/build-and-test-callable.yaml

- name: Generate maximal Reconvergence Tests
  continue-on-error: true
  if: always()
  run: |
      rm -rf OffloadTest/tools/TestGenerator/reconvergence/tests/*
      cd OffloadTest/tools/TestGenerator/reconvergence
      cmake -G Ninja -B build/
      ninja -C build
- name: Run Maximal Reconvergence Test
  continue-on-error: true
  if: always()
  env:
      OFFLOADTEST_SUPPRESS_DIFF: 1
  run: |
      cd llvm-project
      cd build
      ./bin/llvm-lit -v --xunit-xml-output=testresults-max-reconv.xunit.xml ${{ github.workspace }}/OffloadTest/tools/TestGenerator/reconvergence/tests
      
```

We don't plan to store the physical test files in the repo. Developers can still
run the tests locally by running the test generator to output the tests in their
machine.

### Reporting

We may implment an environment variable `OFFLOADTEST_SUPPRESS_DIFF` to filter
out some logs, since for example, diffs will be massive for a failing test.

```cpp
// lib/Support/Check.cpp

if (!std::getenv("OFFLOADTEST_SUPPRESS_DIFF")) {
  OS << "Expected:\n";
  llvm::yaml::Output YAMLOS(OS);
  YAMLOS << *R.ExpectedPtr;
  OS << "Got:\n";
  YAMLOS << *R.ActualPtr;
  ...
}
```

The results of the test will be inspectable separately from the results of the
existing HLSL tests. We may display the result badge of the reconvergence tests
in a separate table in README.md.

### Latency

The entire Vulkan-CTS test (~1500 shaders) takes ~10 seconds to complete, so the
test generation + execution time should be similar and should not significantly
affect the current pipeline duration. We may also choose to start with smaller
iterations (~100 shaders).

### Debugging

Debugging a failed test will be hard, as a randomly generated shader will not be
so intuitive for readers to calculate the expected result at a given line. There
are several ways to help pinpoint a bug:

- Reducing the workgroup size and/or nesting level.
- Comparing the results with other GPUs and/or backends.
- Writing a reducer for the randomly generated shaders.

It is worth noting that failures may originate from driver compilers rather than
the frontend compilers.

### Sanity Check

A small subset of pre-generated tests will be included in the repository to
allow developers to sanity-check without triggering the full pipeline.

## Alternatives considered (Optional)

The proposed solution is the hybrid of the two alternatives considered.

### Option 1: Pre-generate and store all shaders in YAML

This approach involves generating all shaders offline and storing them in the
repository. Although this is a straightforward implementation, it's not
necessary to maintain physical copies of the random shaders. We may later want
to change the parameters of the generator (e.g. seed, nesting level).

### Option 2: Generation and execution in a separate test pipeline

This approach mimics Vulkan-CTS by doing the shader generation, CPU simulation,
and GPU execution in its own test pipeline, without storing any physical copies
at any point in time. However, this requires implementing the entire pipeline
from scratch for multiple backends, including DirectX and Metal.

## Acknowledgments

Steven Perron and Nathan Gauër for reviewing the initial planning and
documentation.
