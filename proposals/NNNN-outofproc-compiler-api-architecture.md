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
compilation work to take advantage of systems that have multiple processors, or
multiple-core processors. A separate compiler process is created for each
available processor. For example, if the system has four processors, then four
compiler processes are created.

The process pool will be associated to an instance of the compiler library
and will live as long as that instance is alive.  Compilation requests will
be blocked waiting for available workers in the pool.

Communication with the process pool will be done using a named pipe IPC
mechanism. Pipe names will be unique to the process that is being communicated
with. Results are sent back over the IPC mechanism.

## Detailed design

A generic compiler api will be used to help frame the out of process
architecture.  The full HLSL compiler api has not been fully designed but the
concepts illustrated here with this example are relavant to any api performing
work in a separte process.

### Out-of-process system initialization

The out of process system will be initialized on the first creation of a 
library instance. All calls into the library flow through that system.

Instances of the compiler library are created using a creation api entrypoint.
Library instances must be destroyed using destroy/dispose api entrypoint.

#### Example Creation api
```c++
/**
* An opaque type representing the compiler library.
*/
typedef void* CompilerInstance;

/**
* Creates an instance of a compiler. Compiler instances must be destroyed by
* calling clang_disposeCompiler.
*/
CompilerInstance clang_createCompiler();

/**
* Destroy the give compiler instance.
*/
void clang_disposeCompiler(CompilerInstance instance);
```

Clients that intend to compile using multiple threads will be required to
create a new api instance per thread. Api calls are synchronous and blocking.


### Singleton initialization and system overview
A singleton manages all state and request traffic from the calling process
using the api. The singleton owns a work dispatching system that operates on a
process pool. Each process in the pool is a worker process that is monitored by
a dedicated thread. One thread to one process.  The thread communicates to its
owned worker process and the singleton's dispatching system. Named pipes are 
used to communicate with woker processes. All work belonging to the api is
dispatched to the worker process. When a worker process completes work, it
exits. The monitoring thread spawns a new process for any exited process to
replenish the process pool.  This includes crashed processes.

On first creation of a compiler instance the following initialization will
occur.

* Create and configure a dispatcher that is able to take api calls and package
them into messages to be sent to the worker process pool.
* Create and configure a worker process pool that creates a thread for each
worker process in the process pool.
    * Each thread connects to the worker process using named pipes enabling
    communication between the thread and its worker process.
    * Each thread configures the worker process to hook stdout/stderr and pipe
    the traffic to a file specified by the thread. This file will be sent back as
    additional status information about the compile operation.

At this point there is a dispatcher connected to a worker pool waiting for
work. 

### Calling apis
Compiler instances are retuired parameters to apis that perform operations like
compiling.  This ensure that the work being performed is tied to an instance.

#### Example entry point that takes a compiler instance
```c++
/**
* Compile with the given shader source and arguments.
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

CompilerResult clang_compile(
    CompilerInstance instance,
    const char* buffer,
    size_t bufferSize,
    const char** args, size_t numArgs,
    CompilerIncludeCallback includeHandler /*(optional)*/);
```

The start of the api call begins at the api entrypoint.  This is where the
system will use the compiler instance and parameters to determine the best
way to dispatch the work to a worker process.

#### The API entrypoint will...
* Package api parameters into the required messsage format
* Send a message with params to the Api call dispatcher
* Wait for completion
* Unpack results
* Return results

#### The API call Dispatcher will...
* Wait for an open worker process
* Send a message with params to the worker thread in the thread pool
* Wait for completion
* Return results to the API entrypoint

#### The worker process monitoring thread will...
* Send a message with params to its monitored worker process over IPC
* Wait for completion
* Read file that contains the captured stdout/stderr traffic and packlage it as
status result data.
* Return results to the api call dispatcher
* Spawn a new worker process

#### The Worker Process will...
* Unpack the message and params from its monitoring thread and call into a
 compiler implementation.
* Wait for completion
* Exit process cleanly / Process crash
    * In both cases, the process will be exited. The monitoring thread will
    always ensure that the contents of the stdout/stderr data is sent back to
    the caller.

### Error handling

If the compiler encounters an error during compilation or the compiler
process crashes, the rest of the compiler processes will continue on.
Error information is communicated back over the IPC mechanism to the caller
and the application will choose how to handle it.

### IPC communication data

A simple IPC payload would be a JSON formatted string value. This gives the
most flexiblity. Existing clang tooling (clangd) uses [json-rpc](https://www.jsonrpc.org/specification)
to communicate between tooling apis and its server component. This out of 
process architecture can leverage existing code in the llvm repo that knows
how to work with JSON and json-rpc formatted messages.

### Examples of JSON
#### JSON Request
```json
{
    "json-rpc":"2.0",
    "method":"compile",
    "params":{
        "arg":"value",
        "arg2":"value2",
        "arg3":"value3",
    },
    "id":1
}
```
#### JSON Response
```json
{
    "json-rpc":"1.0",
    "result":{
        "res":"value",
        "re2":"value2",
    },
    "id":1
}
```
#### JSON Response (error)
```json
{
    "json-rpc":"1.0",
    "error":{
        "res":"value",
        "re2":"value2",
    },
    "id":1
}
```

### The worker process
The compiler driver code for DXC lives in clang-dxc.exe.  This module would be
extended with additional commandline arguments to control its launch behaviors.
Additional params will be used to configure the process startup logic to setup
an IPC mechanism and communicate back to the worker thread that launched it.

Using this same module keeps a single binary for all compilation.

## Alternatives considered

> Caller creates a factory object first and uses that to create compiler
instances.

## Acknowledgments

[Chris Bieneman](https://github.com/llvm-beanz)

<!-- {% endraw %} -->
