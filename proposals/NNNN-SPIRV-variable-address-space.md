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

Reconciliating the SPIR-V & HLSL side could be done in two ways:
 - unify the storage classes in SPIR-V.
 - separate the address spaces in HLSL.

Implementing constant buffers & other resources is done by creating new
address spaces, making explicit the constraints some allocations have.
Thus, it seems separating the address spaces for globals & locals would
allow us to stay consistent with the rest of the language.

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
`Private` storage class. When this selection depends on a runtime condition,
this cannot be lowered to SPIR-V as-is.

## Proposed solution: using 2 HLSL address spaces

Thread-local, global variables will be put in the `hlsl_private` address
space. Thread-local function-local variables will be put in the `default`
address space.

## Implementing the solution

A new address space will be added to Clang: `hlsl_private`.
This address space will be mapped to `Spirv::Private` on the SPIR-V backend,
`PRIVATE_ADDRESS` for AMDGPU, and the address space `0` in DXIL.

Clang codegen will add the new address space annotations, separating
the `private` from the default.

For the time being, the `private` address space will be marked as a subset of
the `default` address space, allowing overload resolution for class methods:
- an object in the `private` address space will be allowed to use a method
  declared with a `this` in the default address space.

Clang will emit an `addrspacecast` we will have to handle, but that's a known
issue in address-space overload resolution, and not new to this proposal.

## Alternative design considered

### Force optimizations, and force inlining

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

- HLSL allows using `noinline`: we would have to ignore it.
- HLSL allows exporting functions to compile to a library: if we need to
  inline to generate functions, we cannot emit libraries exposign such
  functions.
- Runtime conditions causing address-space conflict would require code
  duplication.
- It makes reading the generated assembly harder.

### Move all variables to the function scope

HLSL static globals have a known initialization value at compile-time.
Meaning we could move the global variables to the entrypoint first basic
block, as local variables.
If SPIR-V has no global variables, all pointers as `Function`.
This would require passing references to other functions referencing those
globals, or inline them, but it would be possible.

But the blocker remains the same: building to a library function.
If an exported function references a global variable, we cannot change
the signature of the function.

## Move all variables to the global scope

By moving all local variables to the global scope, we now have a single
storage class `Private`, and won't have conflict issues.
This also allows us to compile non-optimized code, and to keep functions if
required.

HLSL & SPIR-V disallow static recursion. Meaning we know at compile-time
that each function requires one instance of each local variable.
This would also work with exported functions: static recursion is still not
allowed, so cross compile-units recursion is not an issue.

The main issue of this solution can have are:
- drivers may have a harder time figuring out variable lifetimes.
- SPIR-V has a hard 65536 global variable limit (vs 500k local variables).

I believe those 2 are not hard blockers, but something we need to be aware of.

## Selectively move variables to the global scope.

If a variable is only loaded/stored from/to, and remains in the function
scope, there should be no pointer incompatibility.
This means we could potentially implement the solution 4, but only targeting
variables for which addresses are moved across their function scope
boundaries.

This would require additional IR analysis, as we would need to determine
which address is used in another scope to recreate a global variable.

The motivation we could have for such solution are:
- if drivers have a hard time optimizing the global variables.
- if the global variable count limit becomes an issue.

Implementing this solution is more complex, and could be more error prone,
so until we have a real need, I would recommend against, and moving forward
with solution 4. If the need comes, moving from solution 4 to solution 5
would be possible, as it's just an optimization on top.

