<!-- {% raw %} -->

# Implementation of Root Signatures in Clang

* Proposal: [0002](0002-root-signture-in-clang.md)
* Author(s): [Xiang Li](https//github.com/python3kgae), [Damyan
  Pepper](https://github.com/damyanp), [Joao Saffran](https://github.com/joaosaffran)
* Status: **Accepted**
* Impacted Project(s): Clang

<!--
*During the review process, add the following fields as needed:*

* PRs: [#NNNN](https://github.com/microsoft/DirectXShaderCompiler/pull/NNNN)
* Issues:
  [#NNNN](https://github.com/microsoft/DirectXShaderCompiler/issues/NNNN)
  -->

## Introduction

[Root
Signatures](https://learn.microsoft.com/en-us/windows/win32/direct3d12/root-signatures-overview)
can be [specified in HLSL][specify_root_signatures] and included in the
generated DXContainer in a binary serialized format. Support for this
functionality needs to be added to Clang.

This change proposes adding:

* New AST nodes to represent the root signature
* A metadata representation of the root signature so it can be stored in LLVM IR
* Validation and diagnostic generation for root signatures during semantic
  analysis
* Conversion of the metadata representation to the binary serialized format.

[specify_root_signatures]: https://learn.microsoft.com/en-us/windows/win32/direct3d12/specifying-root-signatures-in-hlsl

## Motivation

### What are Root Signatures?

In DirectX HLSL, resources can be associated with registers.  For example:

```c++
StructuredBuffer<float4> b1 : register(t0);
StructuredBuffer<float4> b2 : register(t1);
StructuredBuffer<float4> bn[] : register(t2);
```

In Direct3D 12, resources can be assigned to these registers. Root Signatures
describe how these resources are set using the Direct3D API. A Root Signature
describes a list of root parameters and how they map onto registers. These Root
Signatures are all compatible with the HLSL shown above:

Three parameters - two root descriptors and a descriptor table:

```c++
"SRV(t0),"
"SRV(t1),"
"DescriptorTable(SRV(t1, numDescriptors = unbounded))"
```

This would be set with C++ code that looks like this:

```c++
cl->SetGraphicsRootShaderResourceView(0, buffer1);
cl->SetGraphicsRootShaderResourceView(1, buffer2);
cl->SetGraphicsRootDescriptorTable(2, baseDescriptor);
```

A single parameter that's a descriptor table:

```c++
"DescriptorTable(SRV(t0, numDescriptors = unbounded))"
```

This would be set with C++ code that looks like this:

```c++
cl->SetGraphicsRootDescriptorTable(0, baseDescriptor);
```

The application creates a root signature by passing a serialized root signature
blob to the
[`CreateRootSignature`](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-id3d12device-createrootsignature)
method. This root signature must then be used when creating the Pipeline State
Object and also set on the command list before setting any of the root
parameters.

### Specifying Root Signatures

A serialized root signature blob can be built in an application by using the
[`D3D12SerializeRootSignature`](https://learn.microsoft.com/en-us/windows/win32/api/d3d12/nf-d3d12-d3d12serializerootsignature)
function. However, it is also helpful to be able to provide the shader compiler
with a root signature so that it can perform validation against it and the
shader being compiled. Also, the syntax for specifying a root signature in HLSL
can be more convenient than setting up the various structures required to do so
in C++. A compiled shader that contains a root signature can be passed to
`CreateRootSignature`.

In HLSL, Root Signatures are specified using a domain specific language as
documented [here][specify_root_signatures].

See below for the [grammar](#root-signature-grammar) of this DSL.

An example root signature string (see the documentation for some more extensive
samples):

```
"RootFlags(ALLOW_INPUT_ASSEMBLER_INPUT_LAYOUT), CBV(b0)"
```

A root signature can be associated with an entry point using the `RootSignature`
attribute.  eg:

```c++
[RootSignature("RootFlags(ALLOW_INPUT_ASSEMBLER_INPUT_LAYOUT), CBV(b0)")]
float4 main(float4 coord : COORD) : SV_TARGET {
    // ...
}
```

The compiler can then verify that any resources used from this entry point are
compatible with this root signature.

In addition, when using [HLSL State
Objects](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx-graphics-hlsl-state-object)
root signatures can also be specified using `GlobalRootSignature` and
`LocalRootSignature`, where the same string format is used with the state object. eg:

```c++
GlobalRootSignature my_global_root_signature = { "CBV(b0), SRV(t0)" };
LocalRootSignature my_local_root_signature = { "SRV(t1)" };
```

These root signatures (along with other subobjects) can be associated with
exports from a shader libary like so:

```c++
SubobjectToExportsAssociation my_association = {
    "my_global_root_signature",
    "MyMissShader"
};
```

> Note: HLSL State Objects are out of scope for this proposal, and so support
> for LocalRootSignature and GlobalRootSignature is not covered in this
> document.

#### Note on the root signature domain specific language

We have received feedback that the DSL for root signatures is not something that
every language that targets DirectX would want to adopt. For this reason we need
to ensure that our solution doesn't unnecessarily tie the non-HLSL parts to it.

### Root Signature Grammar

The root signature DSL is defined using a slightly modified version of Extended
Backus-Naur form. Where we assume there is arbitrary whitespace between any
subsequent tokens. Additionally, all keywords and enums are case-insensitive.

```
    RootSignature = [ RootElement { ',' RootElement } ] ;

    RootElement = RootFlags | RootConstants | RootCBV | RootSRV | RootUAV |
                  DescriptorTable | StaticSampler ;

    RootFlags = 'RootFlags' '(' [ ROOT_FLAG { '|' ROOT_FLAG } ] ')' ;

    ROOT_FLAG = 0 | 'ALLOW_INPUT_ASSEMBLER_INPUT_LAYOUT' |
                'DENY_VERTEX_SHADER_ROOT_ACCESS' |
                'DENY_HULL_SHADER_ROOT_ACCESS' |
                'DENY_DOMAIN_SHADER_ROOT_ACCESS' |
                'DENY_GEOMETRY_SHADER_ROOT_ACCESS' |
                'DENY_PIXEL_SHADER_ROOT_ACCESS' |
                'DENY_AMPLIFICATION_SHADER_ROOT_ACCESS' |
                'DENY_MESH_SHADER_ROOT_ACCESS' |
                'ALLOW_STREAM_OUTPUT' |
                'LOCAL_ROOT_SIGNATURE' |
                'CBV_SRV_UAV_HEAP_DIRECTLY_INDEXED' |
                'SAMPLER_HEAP_DIRECTLY_INDEXED' ;

    RootConstants = 'RootConstants' '('
      ( 'num32BitConstants' '=' POS_INT ) ',' BReg
      { ',' RootConstantArgs } ')' ;

    RootConstantArgs =
      ( 'space' '=' POS_INT ) | ( 'visibility' '=' SHADER_VISIBILITY ) ;

    POS_INT = [ + ] DIGITS ;

    ROOT_DESCRIPTOR_FLAGS = 0 | 'DATA_STATIC' |
                            'DATA_STATIC_WHILE_SET_AT_EXECUTE' |
                            'DATA_VOLATILE' ;

    RootCBV = 'CBV' '(' BReg { ',' RootParamArgs } ')' ;

    RootSRV = 'SRV' '(' TReg { ',' RootParamArgs } ')' ;

    RootUAV = 'UAV' '(' UReg { ',' RootParamArgs } ')' ;

    RootParamArgs =
      ( 'space' '=' POS_INT ) |
      ( 'visibility' '=' SHADER_VISIBILITY ) |
      ( 'flags' '=' ROOT_DESCRIPTOR_FLAGS ) ;

    DescriptorTable = 'DescriptorTable' '('
      [ DTClause { : DTClause } ] [ : ( 'visibility' '=' SHADER_VISIBILITY ) ]
    ')' ;

    DTClause : CBV | SRV | UAV | Sampler ;

    DESCRIPTOR_RANGE_FLAGS =
      [ DESCRIPTOR_RANGE_FLAG { '|' DESCRIPTOR_RANGE_FLAG } ] ;

    DESCRIPTOR_RANGE_FLAG = 0 | 'DESCRIPTORS_VOLATILE' |
                            'DATA_VOLATILE' | 'DATA_STATIC' |
                            'DATA_STATIC_WHILE_SET_AT_EXECUTE' |
                            'DESCRIPTORS_STATIC_KEEPING_BUFFER_BOUNDS_CHECKS' ;

    CBV = 'CBV' '(' BReg ClauseArgs ')' ;

    SRV = 'SRV' '(' TReg ClauseArgs ')' ;

    UAV = 'UAV' '(' UReg ClauseArgs ')' ;

    Sampler = 'Sampler' '(' SReg { ',' ClauseArgs } ')' ;

    ClauseArgs =
      ( 'numDescriptors' '=' NUM_DESCRIPTORS_UNBOUNDED ) |
      ( 'space' '=' POS_INT ) |
      ( 'offset' '=' DESCRIPTOR_RANGE_OFFSET ) |
      ( 'flags' '=' DESCRIPTOR_RANGE_FLAGS ) ;

    SHADER_VISIBILITY = 'SHADER_VISIBILITY_ALL' |
                        'SHADER_VISIBILITY_VERTEX' |
                        'SHADER_VISIBILITY_HULL' |
                        'SHADER_VISIBILITY_DOMAIN' |
                        'SHADER_VISIBILITY_GEOMETRY' |
                        'SHADER_VISIBILITY_PIXEL' |
                        'SHADER_VISIBILITY_AMPLIFICATION' |
                        'SHADER_VISIBILITY_MESH' ;

    DESCRIPTOR_RANGE_OFFSET = 'unbounded' | POS_INT ;

    DESCRIPTOR_RANGE_OFFSET = 'DESCRIPTOR_RANGE_OFFSET_APPEND' | POS_INT ;

    StaticSampler = 'StaticSampler' '(' SReg { ',' SamplerArgs }')' ;

    SamplerArgs =
      ( 'filter' '=' FILTER ) |
      ( 'addressU' '=' TEXTURE_ADDRESS ) |
      ( 'addressV' '=' TEXTURE_ADDRESS ) |
      ( 'addressW' '=' TEXTURE_ADDRESS ) |
      ( 'mipLODBias' '=' NUMBER ) |
      ( 'maxAnisotropy' '=' NUMBER ) |
      ( 'comparisonFunc' '=' COMPARISON_FUNC ) |
      ( 'borderColor' '=' STATIC_BORDER_COLOR ) |
      ( 'minLOD' '=' NUMBER ) |
      ( 'maxLOD' '=' NUMBER ) |
      ( 'space' '=' POS_INT ) |
      ( 'visibility' '=' SHADER_VISIBILITY ) ;

    BReg = 'b' DIGITS ;

    TReg = 't' DIGITS ;

    UReg = 'u' DIGITS ;

    SReg = 's' DIGITS ;

    FILTER = 'FILTER_MIN_MAG_MIP_POINT' |
             'FILTER_MIN_MAG_POINT_MIP_LINEAR' |
             'FILTER_MIN_POINT_MAG_LINEAR_MIP_POINT' |
             'FILTER_MIN_POINT_MAG_MIP_LINEAR' |
             'FILTER_MIN_LINEAR_MAG_MIP_POINT' |
             'FILTER_MIN_LINEAR_MAG_POINT_MIP_LINEAR' |
             'FILTER_MIN_MAG_LINEAR_MIP_POINT' |
             'FILTER_MIN_MAG_MIP_LINEAR' |
             'FILTER_ANISOTROPIC' |
             'FILTER_COMPARISON_MIN_MAG_MIP_POINT' |
             'FILTER_COMPARISON_MIN_MAG_POINT_MIP_LINEAR' |
             'FILTER_COMPARISON_MIN_POINT_MAG_LINEAR_MIP_POINT' |
             'FILTER_COMPARISON_MIN_POINT_MAG_MIP_LINEAR' |
             'FILTER_COMPARISON_MIN_LINEAR_MAG_MIP_POINT' |
             'FILTER_COMPARISON_MIN_LINEAR_MAG_POINT_MIP_LINEAR' |
             'FILTER_COMPARISON_MIN_MAG_LINEAR_MIP_POINT' |
             'FILTER_COMPARISON_MIN_MAG_MIP_LINEAR' |
             'FILTER_COMPARISON_ANISOTROPIC' |
             'FILTER_MINIMUM_MIN_MAG_MIP_POINT' |
             'FILTER_MINIMUM_MIN_MAG_POINT_MIP_LINEAR' |
             'FILTER_MINIMUM_MIN_POINT_MAG_LINEAR_MIP_POINT' |
             'FILTER_MINIMUM_MIN_POINT_MAG_MIP_LINEAR' |
             'FILTER_MINIMUM_MIN_LINEAR_MAG_MIP_POINT' |
             'FILTER_MINIMUM_MIN_LINEAR_MAG_POINT_MIP_LINEAR' |
             'FILTER_MINIMUM_MIN_MAG_LINEAR_MIP_POINT' |
             'FILTER_MINIMUM_MIN_MAG_MIP_LINEAR' |
             'FILTER_MINIMUM_ANISOTROPIC' |
             'FILTER_MAXIMUM_MIN_MAG_MIP_POINT' |
             'FILTER_MAXIMUM_MIN_MAG_POINT_MIP_LINEAR' |
             'FILTER_MAXIMUM_MIN_POINT_MAG_LINEAR_MIP_POINT' |
             'FILTER_MAXIMUM_MIN_POINT_MAG_MIP_LINEAR' |
             'FILTER_MAXIMUM_MIN_LINEAR_MAG_MIP_POINT' |
             'FILTER_MAXIMUM_MIN_LINEAR_MAG_POINT_MIP_LINEAR' |
             'FILTER_MAXIMUM_MIN_MAG_LINEAR_MIP_POINT' |
             'FILTER_MAXIMUM_MIN_MAG_MIP_LINEAR' |
             'FILTER_MAXIMUM_ANISOTROPIC' ;

    TEXTURE_ADDRESS = 'TEXTURE_ADDRESS_WRAP' |
                      'TEXTURE_ADDRESS_MIRROR' | 'TEXTURE_ADDRESS_CLAMP' |
                      'TEXTURE_ADDRESS_BORDER' | 'TEXTURE_ADDRESS_MIRROR_ONCE' ;

    COMPARISON_FUNC = 'COMPARISON_NEVER' | 'COMPARISON_LESS' |
                      'COMPARISON_EQUAL' | 'COMPARISON_LESS_EQUAL' |
                      'COMPARISON_GREATER' | 'COMPARISON_NOT_EQUAL' |
                      'COMPARISON_GREATER_EQUAL' | 'COMPARISON_ALWAYS' ;

    STATIC_BORDER_COLOR = 'STATIC_BORDER_COLOR_TRANSPARENT_BLACK' |
                          'STATIC_BORDER_COLOR_OPAQUE_BLACK' |
                          'STATIC_BORDER_COLOR_OPAQUE_WHITE' ;
```

### Root Signature Versioning 

Currently, DirectX supports two "versions" of root signatures: 1.0 and 1.1. 
Version 1.1 includes additional flags for descriptor ranges and root descriptors. 
See the [DirectX Documentation][root_signature_versions_doc] for full details.

The metadata format specification will be the same, regardless of the version. 
Each version has different defaults and different valid flag combinations.
Further details are specified in [validations section](#validations-in-sema)

In the AST, the version is used during parsing, validation and metadata 
generation to enforce compatibility with the metadata representation.

In the metadata representation, this is specified and used to perform  
the correct validation of root signatures, as well as being represented in 
the final object file.

### Validation and Diagnostics

As well as validating that the root signature is syntactically correct, the
compiler must also validate that the shader is compatible with the it. For
example, it must validate that the root signature binds each register that is
used by the shader. Note that only resources referenced by the entry point need
to be bound:

```c++
StructuredBuffer<float4> a : register(t0);
StructuredBuffer<float4> b : register(t1);

// valid
[RootSignature("SRV(t0)")]
float4 eg1() : SV_TARGET { return a[0]; }

// invalid: b is bound to t1 that is not bound in the root signature.
[RootSignature("SRV(t0)")]
float4 eg2() : SV_TARGET { return b[0]; }
```

## Proposed solution

### Driver

A new optional flag called `-hlsl-rootsig-ver` needs to be added in `Options.td` 
and its associated description in `LangOptions.td`. If the flag is not specified, 
the latest supported version of root signature will be selected by default.

### Root Signatures in the AST

A new attribute, `HLSLRootSignatureAttr` (defined in `Attr.td`), is added to
capture the string defining the root signature. `AdditionalMembers` is used to
add a member that retains the version and a member that holds the parsed
representation of the root signature.

Parsing of the root signature string happens in Sema, and some validation and
diagnostics can be produced at this stage. For example:

* is the root signature string syntactically correct?
* is the specified root signature internally consistent?
  * is the right type of register used in each parameter / descriptor range?
  * are all parsed elements correct according to the chosen root signature version?
* is each register bound only once?
* see [Validations in Sema](#validations-in-sema) for full list

The in-memory representation is guaranteed to be valid as far as the above
checks are concerned.

The root signature AST nodes are serialized / deserialized as normal bitcode.

In the root signature DSL, a root signature is made up of a list of "root
elements". The in-memory datastructures are designed around this concept; the
RootSignature class is essentially a vector of variants.

Example:

```c++
RootSignature[
 "RootFlags(ALLOW_INPUT_ASSEMBLER_INPUT_LAYOUT),"
 "CBV(b0, space=1),"
 "StaticSampler(s1),"
 "DescriptorTable("
 "  SRV(t0, numDescriptors=unbounded),"
 "  UAV(u5, space=1, numDescriptors=10, offset=5))"
]
```

When parsed will produce the equivalent of:

```c++
parsedRootSignature = RootSignature{
  Version = Version_1_1,
  RootElements = {
    RootFlags(ALLOW_INPUT_ASSEMBLER_INPUT_LAYOUT),
    RootCBV(0, 1), // register 0, space 1
    StaticSampler(1, 0), // register 1, space 0
    DescriptorTable({
      SRV(0, 0, unbounded, append), // register 0, space 0, unbounded, offset append
      UAV(5, 1, 10, 5) // register 5, space 1, 10 descriptors, offset 5
    })
  }
};
```

### Default Values of Optional Parameters

Many of the parameters of each root element are optional. If they are not
specified they will take the following default values. These comply with
previous documentation [here][specify_root_signatures].

General Parameters:

- `visibility = SHADER_VISIBLITY_ALL`

Root Descriptor Specific:

- `space = 0`

Descriptor Range Specific:

- `numDescriptors = 1`
- `space = 0`
- `offset = DESCRIPTOR_RANGE_OFFSET_APPEND`

Static Sampler Specific:

- `filter = FILTER_ANSIOTROPIC`
- `addressU = TEXTURE_ADDRESS_WRAP`
- `addressV = TEXTURE_ADDRESS_WRAP`
- `addressW = TEXTURE_ADDRESS_WRAP`
- `mipLODBias = 0.f`
- `maxAnsiotropy = 16`
- `comparisonFunc = COMPARISON_LESS_EQUAL`
- `borderColor = STATIC_BORDER_COLOR_OPAQUE_WHITE`
- `minLOD = 0.f`
- `maxLOD = 3.402823466e+38f`

Flags:

As specified in the grammar, '0' denotes there are no flags set.

- `RootFlags = 0`
- `ROOT_DESCRIPTOR_FLAGS` and `DESCRIPTOR_RANGE_FLAGS`
  - Version 1.0:
    - `DATA_VOLATILE`
  - Version 1.1:
    - `CBV`: `DATA_STATIC_WHILE_SET_AT_EXECUTE`
    - `SRV`: `DATA_STATIC_WHILE_SET_AT_EXECUTE`
    - `UAV`: `DATA_VOLATILE`
    - `Sampler`: `0`

### Root Signatures in the LLVM IR

During frontend code generation an IR-based representation of the root signature
is generated from the in-memory data structures stored in the AST. This is
stored as metadata nodes, identified by named metadata. The metadata format
itself is a straightforward transcription of the in-memory data structure - so
it is a list of root elements.

While the attribute is attached to a function, the metadata collects all the
root signatures together, with the initial metadata associating the root
signatures with functions.

Example for same root signature as above:

```llvm
!dx.rootsignatures = !{!2} ; list of function/root signature pairs
!2 = !{ ptr @main, !3, i32 2 } ; function, root signature, version
!3 = !{ !4, !5, !6, !7 } ; list of root signature elements
!4 = !{ !"RootFlags", i32 1 } ; 1 = allow_input_assembler_input_layout
!5 = !{ !"RootCBV", i32 0, i32 1, i32 0, i32 0 } ; register 0, space 1, 0 = visiblity, 0 = flags
!6 = !{ !"StaticSampler", i32 1, i32 0, ... } ; register 1, space 0, (additional params omitted)
!7 = !{ !"DescriptorTable", i32 0, !8, !9 } ;  0 = visibility, range list !8, !9
!8 = !{ !"SRV", i32 0, i32 0, i32 -1, i32 -1, i32 4 } ; register 0, space 0, unbounded descriptors, offset append, flags 4
!9 = !{ !"UAV", i32 5, i32 1, i32 10, i32 5, i32 2 } ; register 5, space 1, 10 descriptors, offset 5, flags 2
```

See [Metadata Schema](#metadata-schema) for details.

The IR schema has been designed so that many of the things that need to be
validated during parsing can only be represented in a valid way. For example, it
is not possible to have an incorrect register type for a root parameter /
descriptor range. However, it is possible to represent root signatures where
registers are bound multiple times, or where there are multiple RootFlags
entries, so subsequent stages should not assume that any given root signature in
IR is valid.

### DX Container Blob Generation

During backend code generation, the LLVM IR metadata representation of the root
signature is converted to data structures that are more closely aligned to the
final file format. For example, root parameters and static samplers can be
intermingled in the previous formats, but are now separated into separate arrays
at this point.

Example for same root signature as above:

```c++
rootSignature = RootSignature(
  Version_1_1,
  ALLOW_INPUT_ASSEMBLER_INPUT_LAYOUT,
  { // parameters
    RootCBV(0, 1),
    DescriptorTable({
      SRV(0, 0, unbounded, append, 0),
      UAV(5, 1, 10, 5, 0)
    })
  },
  { // static samplers
    StaticSampler(1, 0)
  });
```

At this point, final validation is performed to ensure that the root signature
itself is valid. One key validation here is to check that each register is only
bound once in the root signature. Even though this validation has been performed
in the Clang frontend, we also need to support scenarios where the IR comes from
other frontends, so the validation must be performed here as well.

Once the root signature itself has been validated, validation is performed
against the shader to ensure that any registers that the shader uses are bound
in the root signature. This validation needs to occur after any dead-code
elimation has completed.

### Testing
Testing DX Container generation requires a two stage testing strategy.
1. Use Google Test unit tests to create and inspect binary files for specific
   hex values, this is useful for local validation.
2. Cyclic tests, generating YAML from the binary, and then check the other
   way as well.
Some examples are the existing DX Container unit tests. 
Such test infrastructure will require the design and construction of a disassembler
for Root Signature Blob or DX Container.

## Detailed design

### Validations in Sema

#### All the values should be legal.

Most values like ShaderVisibility/ParameterType are covered by syntactical
checks in Sema.
The additional semantic rules not already covered by the grammar are listed here.

- For DESCRIPTOR_RANGE_FLAGS on a Sampler, only the following values are valid
  - For version 1.0, only the value DESCRIPTORS_VOLATILE is valid.
  - For version 1.1, the following values are valid:  
    - 0
    - DESCRIPTORS_VOLATILE
    - DESCRIPTORS_STATIC_KEEPING_BUFFER_BOUNDS_CHECKS

- For DESCRIPTOR_RANGE_FLAGS on a CBV/SRV/UAV
  - For version 1.0, only the value DATA_VOLATILE is valid.
  - For version 1.1, the following values are valid:  
    - 0
    - DESCRIPTORS_VOLATILE
    - DATA_VOLATILE
    - DATA_STATIC
    - DATA_STATIC_WHILE_SET_AT_EXECUTE
    - DESCRIPTORS_VOLATILE | DATA_VOLATILE
    - DESCRIPTORS_VOLATILE | DATA_STATIC_WHILE_SET_AT_EXECUTE
    - DESCRIPTORS_STATIC_KEEPING_BUFFER_BOUNDS_CHECKS
    - DESCRIPTORS_STATIC_KEEPING_BUFFER_BOUNDS_CHECKS | DATA_VOLATILE
    - DESCRIPTORS_STATIC_KEEPING_BUFFER_BOUNDS_CHECKS | DATA_STATIC
    - DESCRIPTORS_STATIC_KEEPING_BUFFER_BOUNDS_CHECKS | DATA_STATIC_WHILE_SET_AT_EXECUTE

- StaticSampler

  - Max/MinLOD cannot be NaN.
  - MaxAnisotropy cannot exceed 16.
  - MipLODBias must be within range of [-16, 15.99].

- Register Value
  The value `0xFFFFFFFF` is invalid.
  `CBV(b4294967295)` will result in an error as it refers past a valid address.

- Register Space
  -The range 0xFFFFFFF0 to 0xFFFFFFFF is reserved.

  `CBV(b0, space=4294967295)` is invalid due to the use of reserved space 0xFFFFFFFF.

- Resource ranges must not overlap.

  `CBV(b2), DescriptorTable(CBV(b0, numDescriptors=5))` will result in an error
  due to overlapping at b2.

  Note that a valid value for `numDescriptors` is `unbounded` and requires
  overlap analysis.


### Metadata Schema

#### Named Root Signature table

```LLVM
!dx.rootsignatures = !{!2}
```

A named metadata node, `dx.rootsignatures` is used to identify the root
signature table. The table itself is a list of references to function/root
signature pairs.

#### Function/Root Signature Pair

```LLVM
!2 = !{ptr @main, !3, i32 2 }
```

The function/root signature associates a function (the first operand) with a
reference to a root signature (the second operand) and its version (the third operand),
following. The valid values for version are:
 * 1: version 1.0
 * 2: version 1.1

#### Root Signature

```LLVM
!3 = !{ !4, !5, !6, !7 }
```

The root signature itself consists of a list of references to root signature
elements.

#### Root Signature Elements

Root signature elements are identified by the first operand, which is a string.
The following root signature elements are defined:

* Root flags ("RootFlags")
* Root constants ("RootConstants")
* Root descriptors ("RootCBV", "RootSRV", "RootUAV")
* Descriptor tables ("DescriptorTable")
* Static samplers ("StaticSampler")

As in the [string representation](#root-signature-grammar) of the root
signature, the elements can appear in any order. This does mean that invalid
root signatures can be represented in the metadata (eg multiple root flags). As
a result of this anything that takes the metadata as input must validate the
incoming metadata, even if the HLSL frontend happens to perform validation
before generating the metadata.

#### Root Flags

```LLVM
!4 = { !"RootFlags", i32 1 }
```

Operands:

* i32: the root signature flags
  ([D3D12_ROOT_SIGNATURE_FLAGS][d3d12_root_signature_flags])

#### Root Constants

```LLVM
!123 = { !"RootConstants", i32 0, i32 1, i32 2, i32 3 }
```

Operands:
* i32: shader visibility ([D3D12_SHADER_VISIBILITY][d3d12_shader_visibility])
* i32: shader register
* i32: register space
* i32: number 32 bit values

#### Root descriptors

Root descriptors come in three flavors, but they have the same structure. The
flavors are:

* Root constant buffer view ("RootCBV")
* Root shader resource view ("RootSRV")
* Root unordered access view ("RootUAV")

```LLVM
!5 = { !"RootCBV", i32 0, i32 1, i32 0, i32 0 }
```

Operands:
* i32: shader visibility  ([D3D12_SHADER_VISIBILITY][d3d12_shader_visibility])
* i32: shader register
* i32: register space
* i32: root descriptor flags ([D3D12_ROOT_DESCRIPTOR_FLAGS][d3d12_root_descriptor_flags])

#### Descriptor Tables

Descriptor tables are made up of descriptor ranges.

```LLVM
!7 = { !"DescriptorTable", i32 0, !8, !9 }
```

Operands:

* i32: shader visibility  ([D3D12_SHADER_VISIBILITY][d3d12_shader_visibility])
* remaining operands are references to descriptor ranges

##### Descriptor Ranges

```LLVM
!8 = !{ !"SRV", i32 0, i32 0, i32 -1, i32 -1, i32 4 }
!9 = !{ !"UAV", i32 5, i32 1, i32 10, i32 5, i32 2 }
```

Operands:

* string: type of range - "SRV", "UAV", "CBV" or "Sampler"
* i32: number of descriptors in the range
  - number of descriptors can take the value of `-1` to denote an `unbounded`
  descriptor range during root signature creation. This must denote the end of
  the table and does not allow the next descriptor range to be appended.
* i32: base shader register
* i32: register space
* i32: offset ([D3D12_DESCRIPTOR_RANGE_OFFSET_APPEND][d3d12_descriptor_range_append])
  - offset can take the value of `-1` which will be interpreted as
  `D3D12_DESCRIPTOR_RANGE_OFFSET_APPEND` when the root signature is created.
  This denotes that this descriptor range will immediately follow the preceding
  range, or, there is no offset from the table start.
* i32: descriptor range flags ([D3D12_DESCRIPTOR_RANGE_FLAGS][d3d12_descriptor_range_flags])

#### Static Samplers

```LLVM
!6 = !{ !"StaticSampler", i32 1, i32 0, ... }; remaining operands omitted for space
```

Operands:
* i32: Filter ([D3D12_FILTER][d3d12_filter])
* i32: AddressU ([D3D12_TEXTURE_ADDRESS_MODE][d3d12_texture_address_mode])
* i32: AddressV ([D3D12_TEXTURE_ADDRESS_MODE][d3d12_texture_address_mode])
* i32: AddressW ([D3D12_TEXTURE_ADDRESS_MODE][d3d12_texture_address_mode])
* float: MipLODBias
* i32: MaxAnisotropy
* i32: ComparisonFunc ([D3D12_COMPARISON_FUNC][d3d12_comparison_func])
* i32: BorderColor ([D3D12_STATIC_BORDER_COLOR][d3d12_static_border_color])
* float: MinLOD
* float: MaxLOD
* i32: ShaderRegister
* i32: RegisterSpace
* i32: ShaderVisibility ([D3D12_SHADER_VISIBILITY][d3d12_shader_visibility])

[root_signature_versions_doc]: https://learn.microsoft.com/en-us/windows/win32/direct3d12/root-signature-version-1-1
[d3d12_root_signature_flags]: https://learn.microsoft.com/en-us/windows/win32/api/d3d12/ne-d3d12-d3d12_root_signature_flags
[d3d12_shader_visibility]: https://learn.microsoft.com/en-us/windows/win32/api/d3d12/ne-d3d12-d3d12_shader_visibility
[d3d12_descriptor_range_append]: https://learn.microsoft.com/en-us/windows/win32/api/d3d12/ns-d3d12-d3d12_descriptor_range
[d3d12_root_descriptor_flags]: https://learn.microsoft.com/en-us/windows/win32/api/d3d12/ne-d3d12-d3d12_root_descriptor_flags
[d3d12_descriptor_range_flags]: https://learn.microsoft.com/en-us/windows/win32/api/d3d12/ne-d3d12-d3d12_descriptor_range_flags
[d3d12_filter]: https://learn.microsoft.com/en-us/windows/win32/api/d3d12/ne-d3d12-d3d12_filter
[d3d12_texture_address_mode]: https://learn.microsoft.com/en-us/windows/win32/api/d3d12/ne-d3d12-d3d12_texture_address_mode
[d3d12_comparison_func]: https://learn.microsoft.com/en-us/windows/win32/api/d3d12/ne-d3d12-d3d12_comparison_func
[d3d12_static_border_color]: https://learn.microsoft.com/en-us/windows/win32/api/d3d12/ne-d3d12-d3d12_static_border_color


### Validations during DXIL generation

#### All the things validated in Sema.

  All the validation rules mentioned in [Validations In Sema](#validations-in-sema)
  need to be checked during DXIL generation as well.
  The difference between checks in Sema and DXIL generation is that Sema could
  rely on syntactical checks to validate values in many cases.
  However, in DXIL generation, all values need to be checked to ensure they
  fall within the correct range:

- RootFlags

  - (RootFlags & 0x80000fff) should equals 0.

- Valid values for ShaderVisibility

  - SHADER_VISIBILITY_ALL
  - SHADER_VISIBILITY_VERTEX
  - SHADER_VISIBILITY_HULL
  - SHADER_VISIBILITY_DOMAIN
  - SHADER_VISIBILITY_GEOMETRY
  - SHADER_VISIBILITY_PIXEL
  - SHADER_VISIBILITY_AMPLIFICATION
  - SHADER_VISIBILITY_MESH

- Valid values for RootDescriptorFlags

  - 0
  - DataVolatile
  - DataStaticWihleSetAtExecute
  - DataStatic

- Valid values for DescriptorRangeFlags on CBV/SRV/UAV
  - For root signature version 1.0 must be DESCRIPTORS_VOLATILE.
  - For root signature version 1.1:
    - 0
    - DESCRIPTORS_VOLATILE
    - DATA_VOLATILE
    - DATA_STATIC
    - DATA_STATIC_WHILE_SET_AT_EXECUTE
    - DESCRIPTORS_VOLATILE | DATA_VOLATILE
    - DESCRIPTORS_VOLATILE | DATA_STATIC_WHILE_SET_AT_EXECUTE
    - DESCRIPTORS_STATIC_KEEPING_BUFFER_BOUNDS_CHECKS
    - DESCRIPTORS_STATIC_KEEPING_BUFFER_BOUNDS_CHECKS | DATA_VOLATILE
    - DESCRIPTORS_STATIC_KEEPING_BUFFER_BOUNDS_CHECKS | DATA_STATIC
    - DESCRIPTORS_STATIC_KEEPING_BUFFER_BOUNDS_CHECKS | DATA_STATIC_WHILE_SET_AT_EXECUTE

- Valid values for DescriptorRangeFlags on Sampler
  - For root signature version 1.0 must be 0.
  - For root signature version 1.1:
    - 0
    - DESCRIPTORS_VOLATILE
    - DESCRIPTORS_STATIC_KEEPING_BUFFER_BOUNDS_CHECKS

- StaticSampler

  - Valid values for Filter

    - FILTER_MIN_MAG_MIP_POINT
    - FILTER_MIN_MAG_POINT_MIP_LINEAR
    - FILTER_MIN_POINT_MAG_LINEAR_MIP_POINT
    - FILTER_MIN_POINT_MAG_MIP_LINEAR
    - FILTER_MIN_LINEAR_MAG_MIP_POINT
    - FILTER_MIN_LINEAR_MAG_POINT_MIP_LINEAR
    - FILTER_MIN_MAG_LINEAR_MIP_POINT
    - FILTER_MIN_MAG_MIP_LINEAR
    - FILTER_ANISOTROPIC
    - FILTER_COMPARISON_MIN_MAG_MIP_POINT
    - FILTER_COMPARISON_MIN_MAG_POINT_MIP_LINEAR
    - FILTER_COMPARISON_MIN_POINT_MAG_LINEAR_MIP_POINT
    - FILTER_COMPARISON_MIN_POINT_MAG_MIP_LINEAR
    - FILTER_COMPARISON_MIN_LINEAR_MAG_MIP_POINT
    - FILTER_COMPARISON_MIN_LINEAR_MAG_POINT_MIP_LINEAR
    - FILTER_COMPARISON_MIN_MAG_LINEAR_MIP_POINT
    - FILTER_COMPARISON_MIN_MAG_MIP_LINEAR
    - FILTER_COMPARISON_ANISOTROPIC
    - FILTER_MINIMUM_MIN_MAG_MIP_POINT
    - FILTER_MINIMUM_MIN_MAG_POINT_MIP_LINEAR
    - FILTER_MINIMUM_MIN_POINT_MAG_LINEAR_MIP_POINT
    - FILTER_MINIMUM_MIN_POINT_MAG_MIP_LINEAR
    - FILTER_MINIMUM_MIN_LINEAR_MAG_MIP_POINT
    - FILTER_MINIMUM_MIN_LINEAR_MAG_POINT_MIP_LINEAR
    - FILTER_MINIMUM_MIN_MAG_LINEAR_MIP_POINT
    - FILTER_MINIMUM_MIN_MAG_MIP_LINEAR
    - FILTER_MINIMUM_ANISOTROPIC
    - FILTER_MAXIMUM_MIN_MAG_MIP_POINT
    - FILTER_MAXIMUM_MIN_MAG_POINT_MIP_LINEAR
    - FILTER_MAXIMUM_MIN_POINT_MAG_LINEAR_MIP_POINT
    - FILTER_MAXIMUM_MIN_POINT_MAG_MIP_LINEAR
    - FILTER_MAXIMUM_MIN_LINEAR_MAG_MIP_POINT
    - FILTER_MAXIMUM_MIN_LINEAR_MAG_POINT_MIP_LINEAR
    - FILTER_MAXIMUM_MIN_MAG_LINEAR_MIP_POINT
    - FILTER_MAXIMUM_MIN_MAG_MIP_LINEAR
    - FILTER_MAXIMUM_ANISOTROPIC

  - Valid values for TextureAddress

    - TEXTURE_ADDRESS_WRAP
    - TEXTURE_ADDRESS_MIRROR
    - TEXTURE_ADDRESS_CLAMP
    - TEXTURE_ADDRESS_BORDER
    - TEXTURE_ADDRESS_MIRROR_ONCE

  - Valid values for ComparisonFunc

    - 0
    - COMPARISON_NEVER
    - COMPARISON_LESS
    - COMPARISON_EQUAL
    - COMPARISON_LESS_EQUAL
    - COMPARISON_GREATER
    - COMPARISON_NOT_EQUAL
    - COMPARISON_GREATER_EQUAL
    - COMPARISON_ALWAYS

  - Valid values for StaticBorderColor

    - STATIC_BORDER_COLOR_TRANSPARENT_BLACK
    - STATIC_BORDER_COLOR_OPAQUE_BLACK
    - STATIC_BORDER_COLOR_OPAQUE_WHITE

  - Comparison filter must have ComparisonFunc not equal to 0.

    When the Filter of a StaticSampler is `FILTER_COMPARISON*`,
    the ComparisonFunc cannot be 0.

#### Resource used in DXIL must be fully bound in root signature.

```
  // B is bound to t1, but no root parameters cover t1.
  Buffer<float> B : register(t1);
  [RootSignature("")]
  void main() : SV_Target {
    return B[0];
  }
```

#### Root Signature Flag must match DXIL.

```
  // Used dynamic resource but missing CBVSRVUAVHeapDirectlyIndexed flag.
  [RootSignature("")]
  void main() : SV_Target {
    Buffer<float> B = ResourceDescriptorHeap[0];
    return B[0];
  }
```

#### Textures/TypedBuffers cannot be bound to root descriptors.

```
  // B is TypedBuffer, but bound as a root descriptor.
  Buffer<float> B : register(t0);
  [RootSignature("SRV(t0)")]
  void main() : SV_Target {
    return B[0];
  }
```

<!--
* Is there any potential for changed behavior?
* Will this expose new interfaces that will have support burden?
* How will this proposal be tested?
* Does this require additional hardware/software/human resources?
-->

### Root Signature Driver Options

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

#### Option `-force-rootsig-ver`

When compiling a shader with a root signature, this option overrides the root
signature version used, where the default is `rootsig_1_1`.

Usage:

```
  -force-rootsig-ver rootsig_1_0
  -force-rootsig-ver rootsig_1_1
```

Behaviour:

 - Validation logic that is specific to the version will be followed, as
described in the [validations section](#validations-in-sema)
 - The serialized RTS0 format will be compliant with specified version

#### Option `-rootsig-define`:

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

#### Target Root Signature Version

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

#### Option `-Qstrip_rootsignature`

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

#### Option `/Frs`

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

## Alternatives considered (Optional)

### Store Root Signatures as Strings

The root signature could be stored in its string form in the AST and in LLVM IR.
There's a simplicity to this, and precedant with some other attributes. However,
it does mean that there will be multiple places where the string needs to be
parsed creating challenges for code organization as well as performance
concerns.

In addition, it unnecessarily ties all parts of the system with the current root
signature DSL, which is something that should we [want to
avoid](#note-on-the-root-signature-domain-specific-language).

### Store Root Signatures in the serialized Direct3D format

Direct3D specifies a serialized format for root signatures, that we will
eventually need to generate in order to populate the DXBC container. One option
would be to generate this early on and store it in the AST / IR.

This approach was not chosen because the serialized format is not well suited to
manipulation and storage in Clang/LLVM, it loses data (eg the language allow a
"DESCRIPTOR_RANGE_OFFSET_APPEND" value that should be resolved in the serialized
format).

In addition, the specific serialized format is subject to change as the
root signature specification evolves and it seems that this is something that
Clang and LLVM should be decoupled from as much as possible.

### Introduce a HLSLRootSignatureDecl

Although the current design does not support HLSL state objects - specifically
the `LocalRootSignature` and `GlobalRootSignature` subobjects - we could
anticipate their needs and add a `HLSLRootSignatureDecl` that could be shared
between `HLSLRootSignatureAttr` and whatever AST nodes are introduces for these
subojects. The problem is that we'd need to design pretty much the entire HLSL
state objects feature to do this properly. Instead, we chose to build a complete
feature without state object support and accept that some refactoring in this
area may be necessary to share code between root signatures in attributes and
root signatures in subojects.

### Deduplicate root signatures

It's possible that the same root signature string could be presented to the
compiler multiple times. An extra layer of indirection in the parsing code could
allow us to avoid parsing the root signature multiple times.

As this would strictly be an optimization and isn't required for correctness,
this is something that will be considered if profiling shows us that

* multiple duplicate root signatures is a common scenario and
* parsing them takes a significant amount of time.

### Reused / share D3D code

We could conceivably just use the D3D12 `D3D12_VERSIONED_ROOT_SIGNATURE_DESC`
datastructures for this, rather than building our own parallel versions. Also,
we could even try and get D3D's serialization code open-sourced so we don't need
to maintain multiple implementations of it. This doesn't mesh well with LLVM
since it would be adding external dependencies. We would also need to ensure
that LLVM can be built in all the host environments it supports - this means
binary dependencies are not viable, and any existing code would likely need to
be reworked so much for portability and comformance with LLVM coding conventions
that the effort would not be worthwhile.

## Acknowledgments (Optional)

<!-- {% endraw %} -->
