# SPIRV - Variable address space

 * Proposal: [NNNN](NNNN-SPIRV-variable-address-space.md)
 * Author(s): [Nathan Gauër](https://github.com/Keenuts)
 * Status: **Design In Progress**

## Introduction

From the HLSL spec:

> HLSL programs manipulates data stored in four distinct memory spaces: thread, threadgroup, device and constant.

Those four groups represents the user-facing semantic, and the group this
proposal will focus on is `thread`.
Following this model, a function local variable and a static global variable
share the same address space.

On the logical SPIR-V side, variables are attached to a storage class. This
is a different name to represent the same thing: an address space.
- A pointer to one storage class is incompatible with a pointer to another.

This proposal will use address space when speaking in HLSL/LLVM-IR terms, and
storage class when speaking in SPIR-V terms.
We will not mention C/HLSL style storage classes (static, volatile, etc).

SPIR-V has 2 interesting storage classes:
 - Function
 - Private
A variable declared with the `Function` storage class must be declared in
the first basic block of a function. It is normaly used to represent function
local variables.

A variable declared with the `Private` storage class is private to the current
invocation/thread, but belongs to the global scope.
This would be the equivalent of a static global variable in HLSL.

Because SPIR-V has 2 storage classes to represent those 2 categories and HLSL
has 1, a simple 1:1 lowering of HLSL variables to SPIR-V is not possible.

## HLSL patterns to look for

This section will explain why some HLSL patterns are hard to lower to SPIR-V.

Note: HLSL does not implement references yet, but we have to make sure our
design would allow us to implement them. For this reason, we'll assume HLSL
has references.

### Example 1:

```hlsl
static int a = 0;

void foo() {
  int b = 0;
}
```

`a` and `b` both share the same address space. But on the SPIR-V side, `a`
must be a `Private` variable, while `b` must be a `Function` variable.
This requires the lowering pass to know the context of a variable.

### Example 2:

```hlsl
static int a = 0;

void foo() {
  int& ref = a;
  int b = ref;
}
```

`a` is still `Private`, `b` still `Function`. But `ref` points to `a`.
In SPIR-V, a variable cannot store a pointer pointing to another storage class.
This means `ref` cannot be stored in a variable in the `Function` class.
If `a` is `Private`, `ref` could only be declared as `Private`.

### Example 3:

```hlsl
static int global = 0;

int& foo(int& input, int select) {
  return select ? input : global;
}

void main(int select) {
  int local;
  int& res1 = foo(local, select);
  int& res2 = foo(global, select);
}
```

`global` is still `Private`.
`local` is `Function`.
In SPIR-V, function declarations contains the return and parameters types,
including the storage classes.
This means, depending on the call-site, and the value of `select`, the
return value and parameter would required either the `Function` or the
`Private` storage class.
As-is, this cannot be emitted in SPIR-V.
One solution we might say have is force-inline everything, and propagate
references down to the final load, removing temporaries, and thus removing
incompatibilities.

This becomes impossible if `foo` is exported, or marked as `noinline`.

## Bad solution 1: using 2 HLSL address spaced

The main issue here boils down to:
HSLS uses 1 address space when SPIR-V would require 2 storage classes.

The first solution would be to require HLSL to use 2 address spaces.
This is not possible as HLSL required global & static variables addresses
to be used interchangeably. (See [this comment](https://github.com/llvm/llvm-project/pull/122103#pullrequestreview-2550483607))

## Bad solution 2: Force optimizations, and force inlining

This solution was mentioned in the example 3.
- force inline all the functions
- eliminate local temporaries by propagating the global variable load/stores.

If those transformations were applied, we could avoid address-conflict
mismatch for pointers, and all we'd have are direct load/stores to global
variables.
Functions returning incompatible references wouldn't exist, allowing us to
generate valid SPIR-V.

Since HLSL generates functions with the `always inline` attribute, this could
have been a valid option. But it has a few flaws:

- HLSL allows using `noinline`.
- HLSL allows exporting functions to compile to a library.
- It makes reading the generated assembly harder.

The 3rd problem is a nice-to-have, but the first 2 are a complete stop.

## Bad solution 3: Move all variables to the function scope

HLSL static globals have a known initialization value at compile-time.
Meaning we could move the global variables to the entrypoint first basic
block, as local variables.
If SPIR-V has no global variables, all pointers as `Function`.
This would require passing references to other functions referencing those
globals, or inline them, but it would be possible.

But the blocker remains the same: building to a library function.
If an exported function references a global variable, we cannot change the signature of the function.

## Solution 4: Move all variables to the global scope

HLSL & SPIR-V disallow static recursion. Meaning we know at compile-time
that each function requires one instance of each local variable.

By moving all local variables to the global scope, we now have a single
storage class `Private`, and won't have conflict issues.
This also allows us to compile non-optimized code, and to keep functions if
required.
This would also work with exported functions: static recursion is still not
allowed, so cross compile-units recursion is not an issue.

The main issue of this solution can have are:
- drivers may have a harder time figuring out variable lifetimes.
- SPIR-V has a hard 65536 global variable limit (vs 500k local variables).

I believe those 2 are not hard blockers, but something we need to be aware of.

## Implementing the solution

This would be implemented as a backend LLVM-IR pass. LLVM-IR would remain
normal: global variables in the global scope, `alloca` in the function scope.

The pass would iteration on all function instructions, and replace each
`alloca` with a global variable with the same type. The initialization will
be set to the zero-value for the type.
Each user will be modified to use the global variable instead of the `alloca`.

Then, each global variable in the default address space would be modified to
be in the address space `10` (SPIR-V Private).

At this stage, we'd have no variable in the default address space, but
some IR operands would still use `ptr` instead of `ptr addrspace(10)`.

The pass would then blindly iterate on all operands (types, variables & instructions),
and modify each `ptr` into a `ptr addrspace(10)` (leaving non-default address
space ptr unchanged).

At this stage, we should have no uses of the default address space left, only
`addressspace(10)` and non-zero address spaces uses for resources/workgroup.

This pass would sadly require some specific instructions fixup, like `gep`,
as they do store some additional state, but that's an implementation detail.
