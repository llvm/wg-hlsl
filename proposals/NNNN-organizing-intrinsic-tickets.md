---
title: "[NNNN] - Organizing Intrinsic Tickets"
params:
  authors:
    - github_username: kmpeng
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

- There is an existing parent issue for implementations in `llvm-project`
  (https://github.com/llvm/llvm-project/issues/99235)
- There is a (closed) parent issue for offload tests for a subset of intrinsics
  in `wg-hlsl` (https://github.com/llvm/wg-hlsl/issues/221)
- There are no consistent links between the implementation tickets and test
  tickets

## Proposed Organization Options

### 1) Parent Issue with Separate Linked Issues
**Structure:**
- 1 parent issue in `wg-hlsl` tracking all intrinsic tickets
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


### 2) Parent Issue with Sub-Issues for Each Intrinsic
**Structure:**
- 1 parent issue in `wg-hlsl` tracking all intrinsics
- Sub-issues under the parent issue for each intrinsic
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

### 3) Parent Issue with a Combined Issue per Intrinsic
**Structure:**
- 1 parent issue in `wg-hlsl` tracking all intrinsics
- 1 combined issue per intrinsic, covering both implementation and offload tests
  - Combined issues would probably live in `wg-hlsl`

**Pros/Cons:**
- Makes it clear that implementation and offload tests should be done together
- Single issue to track for both implementation and tests
- Implementations and tests are done in different repos (from each other and
  from where the issue lives)
- Risk of PRs incorrectly closing the issue early (e.g., implementation PR
  closes issue before tests are complete)
  - Would need to use phrases like "partially fixes" or "contributes to" instead
    of the usual ones in PR descriptions
- Need to migrate/create new issues in `wg-hlsl` for all intrinsics

## Other Considerations

1. **Matrix implementations**: For intrinsics where the implementation/tests are
   complete but matrix support is needed, new tickets will need to be opened.
3. **Scope**: Should this reorganization apply retroactively to all intrinsics,
   or only to new work?
