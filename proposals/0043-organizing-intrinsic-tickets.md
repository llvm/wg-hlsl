---
title: "[0043] - Organizing Intrinsic Tickets"
params:
  authors:
    - kmpeng: Kaitlin Peng
  status: Under Consideration
---


## Introduction

Each HLSL intrinsic needs two components to be considered complete: (1) an
implementation, and (2) offload tests. Currently, the organization of these
tickets is inconsistent and broken up across repositories. This lack of
structure has made it difficult to:
- Track the overall completion status of an intrinsic
- Ensure both the implementation and offload tests are done together
- Onboard new contributors who need to understand the full work of an intrinsic

We need a clearer system where the implementation and offload tests are linked,
especially since we need to open new tickets for matrix implementations soon.


## Current State

- There is a [parent issue](https://github.com/llvm/llvm-project/issues/99235)
  in `llvm-project` tracking all intrinsic implementations
  - Each implementation ticket is linked as a sub-issue
- There is a [(closed) parent issue](https://github.com/llvm/wg-hlsl/issues/221)
  in `wg-hlsl` tracking a subset of offload tests
  - Each test ticket is linked as a sub-issue
- There are a few open, floating test tickets with no parent issue in
  `offload-test-suite` (e.g.
  https://github.com/llvm/offload-test-suite/issues/100)
- There are no explicit links between implementation tickets and test tickets


## New Structure

Implementation tickets will remain organized under the existing `llvm-project`
[parent issue](https://github.com/llvm/llvm-project/issues/99235).
`offload-test-suite` issues will be linked as sub-issues to their corresponding
implementation issue in `llvm-project`. This creates a clear hierarchy where
each implementation issue tracks both the implementation work and its associated
tests.

GitHub has a limit of 100 sub-issues per parent issue, and the `llvm-project`
parent issue is already at this limit. To accommodate new issues, we will group
intrinsics by category into intermediate parent issues under the main parent:

```
llvm-project
└─ Parent Issue: Implement the entire HLSL API set
   ├─ Intermediate Parent Issue: Category A Intrinsics
   │  ├─ Implementation Issue: Intrinsic A
   │  │  └─ offload-test-suite Issue: Intrinsic A
   │  ├─ Implementation Issue: Intrinsic B
   │  │  └─ offload-test-suite Issue: Intrinsic B
   │  └─ ...
   ├─ Intermediate Parent Issue: Category B Intrinsics
   │  ├─ Implementation Issue: Intrinsic C
   │  │  └─ offload-test-suite Issue: Intrinsic C
   │  └─ ...
   └─ ...
```

Categories: pure math/logic, data conversion, synchronization, convergent pure,
resource ops, shader I/O, raytracing  
*(Intrinsics that don't fit under any of these categories will go under the main
parent issue for now)*

This grouping will be applied retroactively to all implementation tickets
(including closed ones) to make room for new issues under the parent. Linking
offload test issues to their corresponding implementation issues will only apply
to open and newly created implementation/test issues.

If an implementation or test issue is currently parented to anything other than
the `llvm-project` parent issue, it will not be reparented. It will instead be
linked in the description of the relevant issue.


## Issue Descriptions

Issue descriptions will contain clear requirements that need to be met rather
than detailed step-by-step instructions. This keeps tickets concise and focused
on the acceptance criteria, allowing contributors to determine the best approach
for their specific intrinsic.


## Matrix Issues

For intrinsics that need matrix support, the approach to creating or updating
issues depends on the current state of the implementation and test tickets:

- If the implementation issue is closed, create a new one in `llvm-project` to
  track matrix implementation
- If the implementation issue is open, update it with matrix requirements
- If the test issue is closed, create a new one in `offload-test-suite` to track
  matrix testing completion
- If the test issue is open, update the test issue with matrix testing
  requirements
- If the test issue doesn't exist, create one in `offload-test-suite` with both
  matrix and non-matrix testing requirements
- Link the test issues as sub-issues of the implementation issues

Since we're still figuring out the requirements for matrix implementations and
tests, each matrix implementation and test issue will link to a central
requirements doc/issue in `wg-hlsl` rather than having requirements written out
in each issue description. This way, we can update requirements in one place
rather than across every individual issue.
