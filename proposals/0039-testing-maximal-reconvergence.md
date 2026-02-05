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

#### 1. Adding `SPV_KHR_maximal_reconvergence` extension and `MaximallyReconvergesKHR` capability. These are Vulkan-specific.

This is an indicator for the driver compilers to respect the above requirement
downstream. The frontend compilers will append these instructions if the
`-fspv-enable-maximal-reconvergence` flag is set.

#### 2. Ensuring the frontend compilers themselves do not alter the state during optimizations.

This is the place that needs extensive testing. In the example below, a compiler
may reorder the code (e.g SimplifyCFG pass) so that statements are moved
inside the branches, producing incorrect results.

| Before Optmization | After Optimization |
| --- | --- |
| <pre><code>if (non_uniform_cond) {<br>   doA(); <br>   Out[...] = waveOperations();<br>} else {<br>   doB(); <br>   Out[...] = waveOperations(); <br>}<br></code></pre> |  <pre><code>if (non_uniform_cond) {<br>   doA(); <br>} else {<br>   doB(); <br>} <br> // Invalid transformation. <br> Out[...] = waveOperations(); </code></pre> |

This kind of optimization should be prevented. In DXC, spirv-opt is used to
optimize when targeting Vulkan. It is aware of HLSL's
Single-Program-Multiple-Data (SPMD) programming model, since spir-v has a
similar programing model.

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

A large number of shader with random control flow will be generated. These
shaders use fixed input buffers and write results to output buffers to verify
which threads are active at each point in the shader.

### CPU Simulation

The expected results will be calculated by simulating the execution of the
shader on the CPU using characteristics of the machine, like wave size. This
will ensure that we can get the expected results on any platform.

### Verification

We will generate a set of yaml test files for the offload-test-suite. For each
shader and wave size (4, 8, 16, 32), a test file will be generated that
executes the shader and verifies that the results match the CPU simulation.

## Detailed design

### Test Generation

Logic from [Vulkan
CTS](https://github.com/KhronosGroup/VK-GL-CTS/blob/main/external/vulkancts/modules/vulkan/reconvergence/vktReconvergenceTests.cpp)
will be ported to produce HLSL.

At a high level, each test generation goes through the following steps:

1. Generate instructions with a random control flow.
2. Calculate the expected results (i.e. CPU simulation).
3. Produce the HLSL shader.
4. Format the shader and expected results for offload-test-suite.


This is an [example](https://github.com/llvm/offload-test-suite/pull/685) of the
test generator and the generated
[tests](https://github.com/llvm/offload-test-suite/pull/620).

#### 1. Random shaders

Random control flow will be produced by a fixed-seed RNG and hard-coded
probabilities. For example, they will determine whether the next instruction
will be a loop, if, switch, etc, and with what conditions. For the random
number generator, we will port one from the dEQP library, which is operating
system independent.

These random instructions are represented in a custom intermediate
representation, to simplify calculating the expected results during the CPU
simulation and later producing HLSL shaders with correct syntax. Each shader
program is represented as a stack of these IR instructions. e.g `OP_IF`,
`OP_BALLOT`, `OP_DO_WHILE`, etc.

#### 2. Expected results

During the CPU simulation, these instructions are popped from the stack, and for
each instruction, active thread masks are calculated and stored in a separate
stack. This is what will be used to calculate the expected results of operations
when any write happens.

There are two types of write operations, storing 1) indices of active threads,
and 2) a constant value. These values will be kept in a separate vector, and
this is the output buffer we will use for the test verification. They will help
determine whether an invalid compiler transformation happened.

Because the program has a random control flow with a random number of writes,
the size of the output buffer is unknown at the start. Therefore, it will also
be calculated in a separate "dry-run" pass, before running the CPU simulation.
It will simply walk-through the instructions and count the number of writes.

#### 3. HLSL translation.

Once the expected results are calculated, the intermediate representations are
lowered to HLSL. Similar to the CPU simulation, each instruction is popped from
the stack and translated to HLSL. (e.g. `OP_ELECT` --> `WaveIsFirstLane()` 
`OP_BALLOT` --> `WaveActiveBallot()`, etc.). This is the part that will be
different from Vulkan-CTS, which produces GLSL shaders.

#### 4. Final test file

At this point, the expected results and shaders are ready to be formatted for
offload-test-suite.

One key thing to note is that each GPU has different wave sizes, and different
wave sizes need different expected results. It's not easy to know the wave size
at the test generation step, since it will require setting up a Graphics
pipeline to query the value.

Therefore, we will prepare the tests in all possible wave sizes (every
power-of-2 between 4 and 32, i.e. 4, 8, 16, 32) and have the test pipeline skip
those that do not match the wave size at test runtime. We will implement
`WaveSizeX` directive and append this condition in the test files. As an
example, a GPU with wave size 32 will have `# UNSUPPORTED: !WaveSize32`.

### Workflow Trigger

Only the code for the **random test generator** will reside in the
offload-test-suite repository. The shaders will be generated as part of the
pipeline. 

#### CMake Target 

We will implement a cmake target `check-hlsl-{platform}-reconvergence`, similar
to the existing targets. Running this will generate the physical tests and run
them.

#### Github Workflow

New steps will be added to the existing workflow at the end:

- Build DXC
- Build LLVM
- Dump GPU Info
- Run HLSL Tests
- **Run Reconvergence Tests**

This way, the execution of existing HLSL tests and the reconvergence tests are
separated.

We don't plan to store the physical test files in the repo. Developers can still
save, run, and inspect the tests locally by running the target in their machine.

### Reporting

Since the output buffer is large, logs can be large if the results don't match.
We will segment the output buffer and verification into multiple buffers and
checks or implment an environment variable to filter out some logs.

If any test fails, it will fail the workflow, so it's noticeable in the badge.
`XFail` instructions will be added appropriately to suppress failures.

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

A small subset of pre-generated tests may be included in the repository for sanity-check.

## Alternatives considered (Optional)

The proposed solution is the hybrid of the two alternatives considered.

### Option 1: Pre-generate and store all shaders in YAML

This approach involves generating all shaders offline and storing them in the
repository. Although this is a straightforward implementation, it's not
necessary to maintain physical copies of the random shaders. We may later want
to change the parameters of the generator (e.g. seed, nesting level).

### Option 2: Generation and execution in a separate test pipeline

This approach mimics Vulkan-CTS by doing the shader generation, CPU simulation,
and GPU execution in its own custom test pipeline, without storing any physical
copies at any point in time. However, this requires implementing the entire
pipeline from scratch for multiple backends, including DirectX and Metal.

## Acknowledgments

Steven Perron and Nathan Gauër for reviewing the initial planning and
documentation.
