---
title: Proposal Template
params:
  number: 0
  authors:
    - github_username: Human Readable Name
  status: Under Consideration
  sponsors:
    github_username: Human Readable Name
---

# Feature name

## Instructions

> This template wraps at 80-columns. You don't need to match that wrapping, but
> having some consistent column wrapping makes it easier to view diffs on
> GitHub's review UI. Please wrap your lines to make it easier to review.

> When filling out the template below for a new feature proposal, please do the
> following first:

> 1. Copy this template to proposals and name it `NNNN-<some unique name>.md`.
>    Do not assign the proposal a number.
> 2. Exclude the "Planned Version", "PRs" and "Issues" from the header as
>    appropriate.
> 3. Fill out the "Introduction", "Motivation", and "Proposed Solution" sections
>    of the template. Do not spend time writing the "Detailed design" until the
>    initial proposal is merged as details will change through design iteration.
> 4. Delete this Instructions section including the line below.
> 5. Post your new proposal for review in a PR and work through review feedback.
> 6. When your PR is approved, _immediately before merging_ update the PR to
>    assign the proposal the highest unused proposal number. Giving each merged
>    proposal a unique number allows it to be easily referred to in issues and
>    project planning.

---

*During the review process, add the following fields as needed:*

* PRs: [#NNNN](https://github.com/llvm/llvm-project/pull/NNNN)
* Issues:
  [#NNNN](https://github.com/llvm/llvm-project/issues/NNNN)
* Posts: [LLVM Discourse](https://discourse.llvm.org/)

## Introduction

10,000 ft view of the change being proposed. Try to keep to one paragraph and
less than 10 sentences.

## Motivation

Describe the problems users are currently facing that this feature addresses.
Include concrete examples, links to related issues, and any relevant background.

The point of this section is not to convince reviewers that you have a solution,
but rather that a problem needs to be resolved.

## Proposed solution

Describe your solution to the problem. Provide examples and describe how they
work. Show how your solution is better than current workarounds: is it cleaner,
safer, or more efficient?

## Detailed design

_The detailed design is not required until the feature is under review._

This section should grow into a full specification that will provide enough
information for someone who isn't the proposal author to implement the feature.
It should also serve as the basis for documentation for the feature. Each
feature will need different levels of detail here, but some common things to
think through are:

* Is there any potential for changed behavior?
* Will this expose new interfaces that will have support burden?
* How will this proposal be tested?
* Does this require additional hardware/software/human resources?
* What documentation should be updated or authored?

## Alternatives considered (Optional)

If alternative solutions were considered, please provide a brief overview. This
section can also be populated based on conversations that occur during
reviewing.

## Acknowledgments (Optional)

Take a moment to acknowledge the contributions of people other than the author
and sponsor.

<!-- {% endraw %} -->
