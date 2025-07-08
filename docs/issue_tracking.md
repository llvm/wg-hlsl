<!-- {% raw %} -->

# Issue Tracking

We use github issues to track the scenarios, deliverables, tasks and bugs for
the HLSL working group.

## HLSL Support project

The [HLSL Support](https://github.com/orgs/llvm/projects/4) github project
brings together issues in the [wg-hlsl](https://github.com/llvm/wg-hlsl) and
[llvm-project](https://github.com/llvm/llvm-project) repos. Sometimes issues are
tracked from external repos if they contribute to the overall goals of the HLSL
working group.

Github projects add custom fields to issues / pull requests that are contained.
The main fields HLSL Support adds are:

### State

* Not set - newly created issues are in this state and are not being actively
  managed.
* Planning - scoping, creating sub-issues. Some amount of review required
  before this can move to the next state.
* Ready - planning is complete, but it isn't being worked on.
* Active - it is being worked on.
* Closed - issue is closed

### Epic

An "Epic" is our name for some large piece of functionality we're working
towards.  All work items associated with an Epic have this field set. We're
still figuring out what is an appropriate scope for an epic. Adding a new epic
is something that should be discussed in the working group meeting.

### Kind

Issues can be:
* Scenario
* Deliverable
* Task
* Bug

Note that we don't use github's new "Type" field because that isn't necessarily
consistent across repos.

More details on what the different kinds of issues are can be found below.

### Iteration

The iteration field specifies when we expect an issue to be closed. 

### Estimate

This is a rough estimate of how long an issue will take to complete.  Values
include:

* Hours, Days, Week, Sprint, Multiple Sprints
* Break Up - this estimate is set to indicate that we think this issues need to
  be broken up into smaller chunks
* Umbrella - this indicates that this issue is actually an "umbrella" one that
  exists to hold multiple sub-issues that are estimated separately.
* n/a - it doesn't always make sense to provide an estimate for an issue, in
  which case we can set it to n/a.

### Blocked

Issues can be blocked for some different reasons:

* PR - waiting for a PR to complete
* Refinement - waiting for agreement that it is ready to go from Planning to
  Ready
* Blocked - waiting for some other dependency before work on this one can
  continue
* Review - waiting on design review

When marking an issue as "Blocked" we try and add a comment on the issue
explaining why.


### Priority

We use the priority field to determine what's most important to work on next.

## Kinds of Issue

### Scenario

A scenario describes a set of things we want to accomplish as part of delivering
an Epic.  Example scenarios: "Implicit Resource Binding", "Offload Testing
Framework".

Generally, we timebox **Planning** for a scenario, usually around 1 week, but
some scenarios may require more planning than others. We track the planning work
with deliverable and task sub-issues. The main goal of planning is to determine
the scope of the scenario and the deliverables that make it up.  Once the
planning deliverable is complete, and has been reviewed, the scenario can move
to the Ready state.

The scenario becomes **Active** once any of its sub-issues become active.  The
scenario is **Closed** once all of its sub-issues are closed.

### Deliverable

Deliverables are sub-issues of Scenarios.  These are major chunks of work that
we expect to complete, usually sequentially, for the scenario.  Example
deliverables: "Build functional tests", "Design", "Implement".

As with scenarios, we timebox **Planning** for a deliverable and work on scoping
the deliverable and identifying tasks during this time. Before the deliverable
can move to the Ready state it needs to be reviewed and all of the task
sub-issues are also Ready. This means that all of the sub-issues have been
estimated.

We move a deliverable to **Active** once we start working on one of the tasks.
At this point we can set the deliverable's iteration based on the estimates of
those tasks.

Once all the tasks are closed, the deliveable can be closed.

### Task

Tasks are the smallest unit of work we track (although we do allow for umbrella
tasks with sub-issues if appropriate). We aim to have tasks that can be
completed in a single iteration.

During task **planning** we work on the scope and plan for the task. If there's
significant design work then this is likely to have been tracked by another
task. After the task has been reviewed and an estimate set it can move to Ready.

When a task goes from **ready** to **active**, we set the iteration to when we
expect to complete it.

### Bug

Bugs are things we didn't plan to do, so we don't spend a lot of time estimating
them. If significant work is involved in fixing it then we'll need to create
other issues to track that as appropriate.


## Implementation Tasks / Bug Tracking

Issues that track tasks or bug fixes that involve changing code in Clang/LLVM
are tracked in the [llvm-project](https://github.com/llvm/llvm-project/issues)
repo.

These labels track issues related to HLSL support in Clang:

* [HLSL][1] - issues related to HLSL language support.
* [backend:DirectX][2] - issues related to the DXIL backend
* [backend:SPIR-V][3] - issues related to the SPIR-V backend

[1]: https://github.com/llvm/llvm-project/issues?q=is%3Aopen+is%3Aissue+label%3AHLSL
[2]: https://github.com/llvm/llvm-project/issues?q=is%3Aopen+is%3Aissue+label%3Abackend%3ADirectX
[3]: https://github.com/llvm/llvm-project/issues?q=is%3Aopen+is%3Aissue+label%3Abackend%3ASPIR-V

<!-- {% endraw %} -->
