<!-- {% raw %} -->

# Support for in-process, Out-of-process, or both for the c style compiler api

* Proposal: [NNNN](NNNN-outofproc-compiler-api-architecture.md)
* Author(s): [Cooper Partin](https://github.com/coopp)
* Sponsor: [Cooper Partin](https://github.com/coopp)
* Status: **Under Consideration**
* Impacted Project(s): (Clang)

* Issues:

## Introduction

An effort is underway to bring compilation support into clang for HLSL based
shaders.  A C style api will be built to enable applications to compile
a shader from their own processes in addition to being able to launching the
clang process.

This document is to propose an architecture for the out-of-process design
approved in Proposal: [0005](0005-inproc-outofproc-compiler-api-support.md).

## Proposed solution

The architecture for an out of process design will behave in a similar way to
the MSBuild design. The system functions as a Process Pool.  This allows the
the compilation work to take advantage of systems that have multiple
processors, or multiple-core processors. A separate compiler process
is created for each available processor. For example, if the system has four
processors, then four compiler processes are created.

The process pool will be associated to an instance of the compiler library
and will live as long as that instance is alive.  Compilation requests will
be queued and the pool of processes that work through compilation requests.

Communication between with the process pool will be done using a named pipe
IPC mechanism. Pipe names will be unique to the process that is being
communicated with. Results are communicated back over the IPC mechanism.

## Detailed design

### Error handling

If the HLSL compiler encounters an error during compilation or the compiler
process crashes, the rest of the compiler processes will continue on.
Error information is communicated back over the IPC mechanism to the caller
and the application will choose how to handle it.

## Alternatives considered

## Acknowledgments

[Chris Bieneman](https://github.com/llvm-beanz)

<!-- {% endraw %} -->
