<!-- {% raw %} -->

# Out-of-process compiler api architecture

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

This document is to propose a more detailed architecture for the approved 
Proposal: [0005](0005-inproc-outofproc-compiler-api-support.md).

## Proposed solution

The architecture for an out of process design will behave in a similar way to
the MSBuild design. The system functions as a Process Pool.  This allows the
compilation work to take advantage of systems that have multiple processors, or
multiple-core processors. A separate compiler process is created for each
available processor. For example, if the system has four processors, then four
compiler processes are created.

The process pool is owned by a singleton object and shared between each api
instance created in the calling process. Compilation requests are blocking
calls. The call will be blocked either waiting for an available worker process
to become available or already dispatched work to be completed.

Communication with the process pool will be done using a named pipe IPC
mechanism. Pipe names will be unique to the process that is being communicated
with. Results are sent back over the IPC mechanism.

## Detailed design

A generic compiler api signature will be used in this document to help frame
the out of process architecture.  The full HLSL compiler api has not been fully
designed but the concepts illustrated here are relavant to any api performing
work in a separte process.

### Out-of-process system initialization

The out of process system is initialized on the first creation of a 
library instance. Api calls into the library flow through a singleton object.

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

Api calls are synchronous and blocking.

### Singleton initialization and system overview
On first creation of a compiler api instance, the singleton object is created.

The singleton object manages all state and request traffic from the calling
process. The singleton contains a work dispatching system that interfaces with a
process pool. Each worker process in the pool is monitored by a dedicated
thread. One thread to one process.

Worker process monitoring threads use named pipes as IPC to communicate with
workers and a different method (TBD) to communicate with the singleton's
dispatching system.

Worker processes exit unconditionally after completing work. The monitoring
thread spawns a new process for any exited process to replenish the process
pool. Exited processes include crashed processes.  Processes that crash are
detected by the monitoring thread allowing error information to be communicated
back through the system.

### Calling apis
Compiler instances are required inputs to compiler api calls. This ensures that
the work being performed is associated to an instance.

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
system uses the compiler instance as a context for the work and the parameters
to determine the best way to dispatch the work to a worker process.

### Roles in the system
#### The API entrypoint
* Package api parameters into the required messsage format
* Send a message with params to the Api call dispatcher
* Wait for completion
* Unpack results
* Return results

#### The API call Dispatcher
* Wait for an open worker process
* Send a message with params to the worker thread in the thread pool
* Wait for completion
* Return results to the API entrypoint

#### The worker process monitoring thread
* Send a message with params to its monitored worker process over IPC
* Wait for completion
* Read file that contains the captured stdout/stderr traffic and packlage it as
status result data.
* Return results to the api call dispatcher
* Spawn a new worker process

#### The Worker Process
* Unpack the message and params from its monitoring thread and call into a
 compiler implementation.
* Wait for completion
* Exit process cleanly / or crash
    * In both cases, the process will be exited. The monitoring thread will
    always ensure that the contents of the stdout/stderr data is sent back to
    the caller.

### Error handling

If the compiler encounters an error during compilation or the compiler
process crashes, the rest of the compiler processes will continue on.
Error information is communicated back over the IPC mechanism to the caller
and the application will choose how to handle it.

### IPC communication data

A JSON message-based protocol similar to [json-rpc](https://www.jsonrpc.org/specification)
is used for packaging parameters and communicating with other processes.
This will provide the most flexiblity. Existing clang tooling (clangd) already
use json-rpc. 

Using the json-rpc protocol enables reuse of existing code in the llvm repo
that supports working withg json-rpc formatted messages. 

> Some investigation may be needed to see if using 100% stock json-rpc protocol
can be used or a rpc-json-like protocol needs to be defined. The json-prc
notification system may not work well with how include handlers may need to be
implemented.

### Examples of JSON-RPC messages
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
    "json-rpc":"2.0",
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
    "json-rpc":"2.0",
    "error":{
        "res":"value",
        "re2":"value2",
    },
    "id":1
}
```

### The worker process
The compiler driver code for DXC lives in clang-dxc.exe.  This module will be
extended with additional commandline arguments and launch behaviors.
Additional params will be used to configure the process startup logic to setup
the required IPC for communicating back to the thread that launched it.

Using this same module keeps a single shipping binary for all compilation.

## Alternatives considered

> Caller creates a factory object first and uses that to create compiler
instances.

## Acknowledgments

[Chris Bieneman](https://github.com/llvm-beanz)

<!-- {% endraw %} -->
