<!-- {% raw %} -->

# Issue Tracking

Issues are used to track all aspects of the project, from the roadmap, through
to milestones and workstreams, to individual tasks / bugs.

## HLSL Support project

The [HLSL Support](https://github.com/orgs/llvm/projects/4) github project
brings together issues in the [wg-hlsl](https://github.com/llvm/wg-hlsl) and
[llvm-project](https://github.com/llvm/llvm-project) repos. This project is used
to manage scheduling work, tracking size and priority estimates as well as
workstreams and milestones.

## Project Milestones

In order to understand progress being made across the entire project, a set of
Milestones are defined. We track these with issues rather than using github's
first-class milestone feature since github milestones are set per-repo and we
want to be able to link issues to milestones across repos.

A milestone issue can be identified by the HLSL Support project's "Category"
field being set to "Project Milestone".

The current target date for hitting a milestone is in the "Target" field.

The current list of milestones can be seen on the [Milestones
view](https://github.com/orgs/llvm/projects/4/views/15). The [Roadmap
view](https://github.com/orgs/llvm/projects/4/views/12) also provides a
graphical view of the milestones over time.

The main body for a Milestone issue follows this format:

* Preamble - text providing information about the milestone, what the goals are,
  what the challenges might be, why it is an interesting milestone etc.
* Workstreams - a list of workstreams, and the workstream milestones that
  contribute to this one.
* Postnote - additional text after the workstream list.

The Workstreams section starts with the heading `## Workstreams` and ends either
at the end of the body, or at a horizontal rule (`---`). The contents of this
section is entirely derived from the Workstream issues and is kept up to date
using the [hlslpm](../tools/hlslpm/README.md) tool.

## Workstreams

The work involved in adding HLSL Support has been split into a number of
workstreams. The [Workstreams
view](https://github.com/orgs/llvm/projects/4/views/16) shows a list of current
workstreams.

A workstream issue can be identified by the "Category" field set to "Workstream".

The workstream issue is formatted similarly to a milestone issue:

* Preamble
* Milestones
* Postnote

The Milestones section starts with the header `## Milestones`. This section is the authority for what gets aggregated into the milestone issues.


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
