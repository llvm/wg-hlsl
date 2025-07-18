<!-- {% raw %} -->

# Root Signature Driver Options

* Proposal: [NNNN](NNNN-root-signture-driver-options.md)
* Author(s): [Finn Plummer](https//github.com/inbelic)
* Status: **Accepted**
* Impacted Project(s): Clang

## Introduction

A user can compile and use a root signature for a shader using a variety of
different command line options. This section lists the options available in DXC
that will be carried forward to Clang and their expected behaviour.

Options implemented in Clang follow the guiding principle to validate as much
as possible on the smallest set of root signatures. Practically, this means
that if a root signature will not be used, then it will not be parsed or
validated.

DXC also provided numerous options that (alongside `-dumpbin`) were intended to
to modify the compiled DXIL Container with respect to the root signature (RTS0)
part. It has been decided that these options will not be implemented in Clang
as a driver option. Instead they will have their functionality implemented
separately within an object manipulation tool.

Concretely, these DXC options are: `setrootsignature`, `extractrootsignature`,
and, `verifyrootsignature`.

### Option `-force-rootsig-ver`

When compiling a shader with a root signature, this option overrides the root
signature version used, where the default is `rootsig_1_1`.

Usage:

```
  -force-rootsig-ver rootsig_1_0
  -force-rootsig-ver rootsig_1_1
```

Behaviour:

 - Validation logic that is specific to the version will be followed
 - The serialized RTS0 format will be compliant with specified version

### Option `-rootsig-define`:

Overrides the root signature attribute for the entry function to be the root
signature defined by the given macro expansion.

Usage:

Given a defined macro either provided in the source file
(`#define RS "CBV(b0)"`), or, as a command line define
(`-D RS="CBV(b0)"`)

```
  -rootsig-define RS
```

Behaviour:

 - If the entry function does not have a root signature attribute, it will use
the one defined by the macro expansion
 - If the entry function has a root signature attribute, it will overwrite to
use the one defined by the macro expansion

_Note_: Behaviour differs from DXC as it will not parse the function's root
signature attribute, if it exists

### Target Root Signature Version

Compiles the "entry" root signature, specified by the given macro expansion, to
a DXIL Container with just the (version specific) RTS0 part.

Usage:

Given a defined macro in the source file (`#define RS "CBV(b0)"`)

```
  -T <root signature version> -E <entry root signature>
  -T <root signature version> -E <entry root signature> -D <entry root signature>="..."
  -T rootsig_1_0 -E RS /Fo RS.bin
  -T rootsig_1_1 -E RS /Fo RS.bin
```

Behaviour:

 - Parse and perform syntactic validations of "entry" root signature
 - Perform the non-resource binding sub-set of validations
 - Produces a DXIL container with just the RTS0 part

_Note_: It is not possible to use `-rootsig-define` to overwrite which root
signature will be used as the "entry" root signature, because this is specified
using the `-E` option when compiling directly to a root signature target.

_Note_: It is possible to specify the root signature using the `-D` option.
This then should not require providing a source file. DXC still requires an
input file, so it will be left as an implementation detail of whether or not it
is feasible to have an optional source file.

### Option `-Qstrip_rootsignature`

Omits the root signature part (RTS0) from the produced DXIL Container.

Usage:

```
  -Qstrip_rootsignature
```

Behaviour:

 - Parse and perform validations of used root signature
 - Produces the DXIL container with the RTS0 omitted

_Note_: Behaviour differs from DXC as it will perform resource binding
validations since this information is available.

### Option `/Frs`

Specifies to compile the shader as normal but will also output the RTS0 part
into a separate DXIL Container.

Usage:

```
  /Frs <DXIL Container>
```

Behaviour:

 - Creates a separate compiler action to output a DXIL Container with just RTS0
part into the file specified.
 - Parses and validates the entry function's root signature.

## Acknowledgments (Optional)

<!-- {% endraw %} -->
