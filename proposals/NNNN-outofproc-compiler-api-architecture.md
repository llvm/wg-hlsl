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

This document is to propose a detailed architecture for the approved 
Proposal: [0005](0005-inproc-outofproc-compiler-api-support.md).

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

A good way to frame the out of process architecture is to use examples that
are more concrete to what it will be used to build.  In this document the
HLSL compiler api will be the example.  The full HLSL compiler api has not been
fully designed but the concepts illustrated here are relavant.

### Library creation and lifetime
Instances of the compiler library are created using
clang_createHlslCompiler(). Library instances must be destroyed
using clang_disposeHlslCompiler().

```c++
/**
* An opaque type representing the compiler library.
*/
typedef void* HlslCompilerInstance;

/**
* Creates an instance of a compiler. Compiler instances must be destroyed by
* calling clang_disposeHlslCompiler.
*/
HlslCompilerInstance clang_createHlslCompiler();

/**
* Destroy the give compiler instance.
*
* Any compilations in progress associated with specified instance will be
* cancelled.
*/
void clang_disposeHlslCompiler(HlslCompilerInstance instance);
```
Compiler instances are reference counted and factoried out from a singleton
instance that is created when the first library instance is created.

Clients that compile using multiple threads will be required to create a new
api instance per thread.

`TODO: Diagram here showing singleton factory`

### Singleton Design overview
The singleton manages all state and request traffic from the calling process
via the api. The singleton owns a work dispatching system that manages a
process pool. Each process in the pool is considered a worker process and is
monitored by a separate thread that communicates to it using named pipes IPC
mechanism. All work is performed in these worker processes. When the worker
process finishes work, it exits and the monitoring thread spawns a new process
in its place in the pool. The thread then waits for more incoming work from the
api call dispatcher.

#### Api entrypoint
* Package api parameters into the required messsage format
* Send a message with params to the Api call dispatcher
* Wait for completion
* Unpack results
* Return results

#### Api call Dispatcher
* Wait for an open worker process
* Send a message with params to the worker thread in the thread pool
* Wait for completion
* Return results to api entry point

#### Thread
* On first startup
    * Launch worker and configure IPC mechanism
    * Send a message to worker to hook stdout/stderr and route them to a specified file path
    ( This gets used later when the caller needs the outputs from the worker that
    gets spewed during compilation.)
* Send a message with params to worker using IPC mechanism
* Wait for completion
* Read and package the stdout/stderr traffic captured in a file configured on thread
startup with the worker process into data to return to the dispatcher.
* Return results to the api call dispatcher
* Spawn a new worker process

#### Worker Process
* On first startup
    * Esablish IPC communication with monitoring thread
    * Route stdout/stderr to a file path passed to it from the monitoring worker
    thread.
* Unpack the message and params and calls into a compiler implementation to
perform work.
* Wait for completion
* Exit process

### Calling apis

Compiler instances are passed to different functions to perform operations like
compiling a shader.  This ensure that the work being performed is tied to a
specific instance.

#### Example entry point that takes a compiler instance
```c++
/**
* Compile a shader with the given shader source and arguments.
* 
* /param instance the compiler instance
* 
* /param buffer a pointer to a buffer in memory that holds the contents of a
* source file to compile, or a NULL pointer when the file is specified as a
* path in the arguments array.
*
* /param bufferSize the size of the buffer.
*
* /param args an array of arguments to use for compilation
*
* /param numArgs the number of arguments in /p args.
* 
* /param includeHandler a callback function for supplying additional
* includes ondemand during compilation. This parameter is optional.
*/

HlslCompilerResult clang_compileHlsl(
    HlslCompilerInstance instance,
    const char* buffer,
    size_t bufferSize,
    const char** args, size_t numArgs,
    HlslCompilerIncludeCallback includeHandler /*(optional)*/);
```



### Error handling

If the HLSL compiler encounters an error during compilation or the compiler
process crashes, the rest of the compiler processes will continue on.
Error information is communicated back over the IPC mechanism to the caller
and the application will choose how to handle it.

## Alternatives considered

## Acknowledgments

[Chris Bieneman](https://github.com/llvm-beanz)

<!-- {% endraw %} -->
