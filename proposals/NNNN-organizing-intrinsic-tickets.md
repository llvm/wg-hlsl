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
- There is a [parent issue](https://github.com/llvm/wg-hlsl/issues/237) in
  `wg-hlsl` tracking implementation of intrinsics unique to MiniEngine 
  - No sub-issues, just one-directional links to the implementation tickets in
    `llvm-project`
  - Manually updated
- There is a [parent issue](https://github.com/llvm/wg-hlsl/issues/239) in
  `wg-hlsl` tracking offload tests for intrinsics unique to MiniEngine 
  - Has sub-issues made in `wg-hlsl` for each intrinsic test, with
    one-directional links to the test tickets in `offload-test-suite`
  - Manually updated
- There are a few open, floating test tickets with no parent issue in
  `offload-test-suite` (e.g.
  https://github.com/llvm/offload-test-suite/issues/100)
- There are no explicit links between implementation tickets and test tickets

## Proposed Reorganization Options

### 1) Parent Issue with Separate Linked Issues
**Structure:**
- 1 parent issue in `wg-hlsl` tracking all intrinsic issues
- Separate issues for implementation (`llvm-project`) and offload tests
  (`offload-test-suite`) for each intrinsic
- Both issues listed under the parent, mixed together
- Bidirectional links within each issue between the implementation and test

**Pros/Cons:**
- Implementation and test issues are in the repos where they need to be
  completed
- Only concrete link between the implementations and tests are within the issues
  themselves
- Parent issue might look cluttered with mixed entries

**Questions:**
- Should we actually change the linked parent of the separate
  implementation/test issues to the `wg-hlsl` issue? Or should the `wg-hlsl`
  issue just manually list the intrinsic tickets (like
  https://github.com/llvm/wg-hlsl/issues/237)?
  - GitHub has a limit of 100 sub-issues under a single issue, so actually
    linking them might cause a problem
  - Listing means no concrete link between the issues and needing to manually
    update the `wg-hlsl` issue

### 2) Parent Issue with Sub-Issues for Each Intrinsic
**Structure:**
- 1 parent issue in `wg-hlsl` tracking all intrinsics
- Sub-issues in `wg-hlsl` under the parent issue for each intrinsic
- Separate issues for implementation (`llvm-project`) and offload tests
  (`offload-test-suite`) nested under each sub-issue

**Pros/Cons:**
- Technically the most organized and hierarchical in appearance
- Don't need bidirectional links within the issues since both are under the same
  sub-issue
- Implementation and test issues are in the repos where they need to be
  completed
- Adds an extra layer of hierarchy to navigate
- Feels a little overkill

**Questions:**
- (Same as option 1) Should we actually change the linked parent of the separate
  implementation/test tickets to the sub-issues? Or should the sub-issues just
  manually list the intrinsic tickets?
  - Listing means no concrete link between the issues and needing to manually
    update the `wg-hlsl` issue

### 3) Parent Issue with a Combined Issue per Intrinsic
**Structure:**
- 1 parent issue in `wg-hlsl` tracking all intrinsic issues
- 1 combined issue per intrinsic, covering both implementation and offload tests
  - These would probably live in `wg-hlsl`

**Pros/Cons:**
- Makes it clear that implementation and offload tests should be done together
- Single issue to track for both implementation and tests
- Implementations and tests are done in different repos (from each other and
  from where the issue lives)
- Risk of PRs incorrectly closing the issue early (e.g., implementation PR
  closes issue before tests are complete)
  - Would need to use phrases like "partially fixes" or "contributes to" instead
    of the usual ones in PR descriptions

**Questions:**
- Would we transfer the existing implementation/test issues to `wg-hlsl` and
  edit them, or create completely new ones?
  - If creating new ones, should we close the old ones that are under other
    repos?


## Other Considerations

1. **Matrix implementations**: For intrinsics where the implementation/tests are
   complete but matrix support is needed, new tickets will need to be opened.
2. **Level of detail in descriptions**: How much detail should we go into for
   each implementation/test issue? Previously we've found we went into too much
   detail, resulting in some of it being confusingly irrelevant to the actual
   issue.
3. **Existing parent issues**: All the reorganization options might involve
   moving existing tickets under a new parent issue, such that the existing
   parent issues will be left with no open tickets. What should we do with them?
   Close them or keep them open as a secondary tracker in that repo?
4. **Scope**: Should this reorganization apply retroactively to all intrinsics,
   or only to new work?
