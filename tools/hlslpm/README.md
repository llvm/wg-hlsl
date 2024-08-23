<!-- {% raw %} -->

# hlslpm

This tool helps manage github issues tracking the [LLVM HLSL
Support](https://github.com/orgs/llvm/projects/4) project. Currently it has
functionality to roll up data from "Workstream" isues into "Milestones", but
this may be extended in the future.

See [issue_tracking.md](../../docs/issue_tracking.md) for details on how these
issues are used.

## Usage

### Requirements

This was tested against Python 3.10.11 with no additional modules installed.

### Generate a PAT

The tool reads and writes from github and uses a Personal Access Token to
authenticate.  Generate a github Personal Access Token (eg from
https://github.com/settings/tokens) save it in a file called "pat.txt". Do not
commit this file (it is listed in the .gitignore to make it hard to accidentally
commit it).

### Running

* Running `python hlslpm.py` will cause the script to do everything apart from
write the results back to github.

* Running `python hlslpm.py --save` will cause the script to write out the
  before and after contents of the issues under the 'output' directory. Diffing
  these directories allows inspection of the changes that would be made.

* Running `python hlslpm.py --update` will cause the script to update the github
  issues that have changed.


## Implementation Notes

### GraphQL

The [HLSL Support project](https://github.com/orgs/llvm/projects/4) is a V2
project in github. These are only exposed through github's [GraphQL
API](https://docs.github.com/en/graphql). Therefore, all the code in this script
is based on GraphQL rather than the traditional REST API.

The VSCode GraphQL extension uses the [schema](schema.docs.graphql) contained in
this repo to provide intellisense. This seems to work best in Python projects if
the GraphQL code is stored in individual files.

### Tests

Some automated tests, built using
[`unittest`](https://docs.python.org/3/library/unittest.html), exist in
[testIssues.py](testIssues.py).

Some individual .py files have some manual tests included in them when they're
run as the main script.

<!-- {% endraw %} -->
