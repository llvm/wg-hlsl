---
title: "[NNNN] - Organizing Intrinsic Tickets"
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

This grouping will be applied retroactively to existing implementation tickets
so that there is room to add new issues under the parent. Linking completed
offload test issues to their corresponding implementation issues will only apply
to new work.


## Matrix Implementation Tickets

For intrinsics that need matrix support, the approach depends on the current
state of the implementation and test tickets:

- If the implementation issue is closed or doesn't exist, create a new one in
  `llvm-project` to track matrix implementation
- If the implementation issue is open, update it with matrix requirements
- If the test issue is closed or doesn't exist, create a new one in
  `offload-test-suite` to track matrix testing completion
- If the test issue is open, update it with matrix testing requirements
- Always link the test issue as a sub-issue of the implementation issue


## Issue Descriptions

Issue descriptions will contain clear requirements that need to be met rather
than detailed step-by-step instructions. This keeps tickets concise and focused
on the acceptance criteria, allowing contributors to determine the best approach
for their specific intrinsic.


## Questions
1) What are the categories we can group the intrinsics into?