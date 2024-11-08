# SPIR-V Input/Output built-ins

 * Proposal: [NNNN](NNNN-spirv-input-builtin.md)
 * Author(s): [Nathan Gauër](https://github.com/Keenuts)
 * Status: **Design In Progress**

## Introduction

HLSL has semantic input/outputs parameters used to carry information
to and from a shader, e.g: the system semantic `SV_GroupID` or `MY_SEMANTIC`,
a user-defined semantic.

In SPIR-V, those are translated to `Input` and `Output` variables,
with either a `BuiltIn` or `Location` decoration.

Example:

```hlsl
float4 vsmain(float4 Position : POSITION) : SV_POSITION
{
  return Position;
}
```

Both `POSITION` and `SV_POSITION` will be represented as an `OpVariable`:

- `POSITION` will have the `Input` storage class.
- `SV_POSITION` will have the `Output` storage class.

- `POSITION` will be decorated with `Location 0`.
- `SV_POSITION` will be decorated with `BuiltIn Position`.

In addition, users can define their own SPIR-V built-ins using inline SPIR-V:

```hlsl
[[vk::ext_builtin_input(/* NumWorkGroups */ 24)]]
static const uint3 myBuiltIn;
```

This document explain how we plan on implementing those in Clang/LLVM.

## Proposed Solution

## Static behaving like an external & LLVM

The current HLSL syntax for inline SPIR-V requires those built-ins to be
`static [const]` variables. The rational was those variables were private to
the invocation, and thus could be written/read without any concurrency issues.
This was fine in DXC as we had our own AST->SPIR-V lowering.

In Clang/LLVM, that's different: such static variable can be optimized in many
ways:
aggressive ways.
 - A non-initialized `static const` is not allowed.
 - Any dead-store to a `static int` can be removed.
 - Meaning any pure computation parent to this store can be removed.

Solving this can be done in 3 ways:
 - Change the spec, allowing the syntax to be less "magical": use `extern`.
 - Fixup the storage class of those variables in Clang.
 - Emit an external constructor & destructor for those preventing optimization.

I'd be in favor of the first solution, which correctly expresses in HLSL what
those built-in variables are, see this
[spec issue](https://github.com/microsoft/hlsl-specs/issues/350).
If we emit those as `extern [thread_local]`, everything works out of the box,
and HLSL feels less magical.

The second solution is to patch Clang to add corner cases for HLSL:
 - allow a `static const` to be left uninitialized.
 - patch the storage class from `SC_Static` to `SC_Extern`
Advantage: we keep the spec as-is, but we add hacks in Clang.

Third solution: keep the static, but add a CXXConstructor which calls a
target-specific intrinsic `load_builtin`. Advantage is Clang already has the
code to handle global initializers, so generating those is OK.
For the output, we'd need to do the opposite: insert another intrinsic
`store_builtin` at the end, which will make sure stores to the variable as not
optimized away.
The disadvantage is we need to emit more target-specific code in the
entry point, meaning more maintenance.

## Frontend changes

Once we solved the variable issue, we need two additional bit of information
to emit proper SPIR-V:
 - the SPIR-V storage class: `Input` or `Output`.
 - the attached `BuiltIn` or `Location` decoration.

The plan is to add:
- 2 new attributes: `HLSLInputBuiltin` and `HLSLOutputBuiltin`
- 2 new address spaces: `vulkan_input` and `vulkan_output`

The TD file will attach each attribute to a `SubjectList` with the following
constraints:

```
HLSLInputBuiltin:  S->hasGlobalStorage() &&
                   S->getStorageClass()==StorageClass::SC_Extern &&
                   S->getType().isConstQualified()

HLSLOutputBuiltin: S->hasGlobalStorage() &&
                   S->getStorageClass()==StorageClass::SC_Extern &&
                   !S->getType().isConstQualified()

def HLSLVkExtBuiltinInput: InheritableAttr {
  let Spellings = [CXX11<"vk", "ext_builtin_input">];
  let Args = [IntArgument<"BuiltIn">];
  let Subjects = SubjectList<[HLSLInputBuiltin], ErrorDiag>;
  let LangOpts = [HLSL];
}

def HLSLVkExtBuiltinOutput: InheritableAttr {
  let Spellings = [CXX11<"vk", "ext_builtin_output">];
  let Args = [IntArgument<"BuiltIn">];
  let Subjects = SubjectList<[HLSLOutputBuiltin], ErrorDiag>;
  let LangOpts = [HLSL];
}
```

When this attribute is encountered, the global variable address space is
changed to either `vulkan_input` or `vulkan_output`.
Then, a `MDNode` is attached: `spirv.Decorations`, adding the `BuiltIn`
decoration using the int argument of the attribute.

Finally, for input/output parameters, we will; skip the attribute, but create
the same global variable with corresponding `vulkan_` address space, and
the `spirv.Decorations` metadata.

The `llvm::Value` passed to the function will be a load from this global
variable.


## What if we don't change the spec and keep static

The change mentioned above assumes we move to an `external`. In case we decide
not to change the HLSL spec, this still holds.
What changes is:
 - Attr.td: constraint will need to check `SC_Static`
 - global variable: a construction **will** be required OR storage class
   is changed to `SC_External` internally.
 - Sema has to be updated to allow `const static int MyVar;` to be legal.

## Backend changes

The SPIR-V backend already supports the `spirv.Decorations` metadata, so this
part works already.

What's required is to add the translation from the `LangAS` `vulkan_input` and
`vulkan_output` to `Input` and `Output` storage class. This is quite trivial
as we already rely on the address space to determine the `OpVariable` storage
classes.

## Draft PR

https://github.com/llvm/llvm-project/pull/115187



