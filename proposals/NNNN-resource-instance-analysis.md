* Proposal: [NNNN - Resource Instance Analysis](NNNN-resource-instance-analysis.md)
* Author(s): [Ashley Coleman](https://github.com/V-FEXrt)
* Status: **Design In Progress**

## Introduction

This proposal introduces a new term, Resource Instance, which represents a 
unique and specific resource. The instance is referenced via a handle returned
from the create handle intrinsics and it is possible to have multiple handles
pointing at a specific Resource Instance, but each unique instance is
disambiguated by the handle creation parameters.

Beyond creation parameters, Reource Instances have several pieces of associated
metadata. Type, CounterDirection (HasCounter), and GloballyCoherent are
identified examples. Type is currently handled well so this proposal suggests
no changes. However CounterDirection and GloballyCoherent require careful late 
stage analysis to derive the correct metadata.

To serve the needs of CounterDirection and to setup a framework for future
instance metadata this document proposes that instance analysis be combined
into the DXILResourceBindingAnalysis pass and that the pass be renamed.


## Proposed solution

In order to support the generic resource instance analysis `DXILResourceBindingAnalysis` 
and `ResourceBindingInfo` will be renamed to `DXILResourceAnalysis` and `ResourceInfo`
respectively. Then associated instance metadata will be resolved during the
`DXILResourceBindingAnalysis` pass.


The following mechanical changes are required to align existing and inflight code
to the new structure.

- `CounterDirection` will supercede `HasCounter` which will be removed from `TypeInfo`
- `CounterDirection` and `GloballyCoherent` will be added to `ResourceInfo`
- `DXILResourceAnalysis` will have a new step to resolve the instance's counter direction.

Certain generated DXIL can create an illegal state for the instance metadata
such as an instance with both an incremented and decremented counter. When this
occurs the analysis pass should prioritize performance for the common case and
defer detailed error message calculation for the uncommon failure code path.

To achieve that goal, a step in `DXILResourceAnalysis` may set a terminal or
invalid value in the ResourceInfo that a later pass `DXILPostOptimizationValidationPass`
will detect and do more expensive processing to raise useful Diagnostics.

It's important to note that in general Diagnostics should not be raised in passes
as they may be invalidated an reran several times however in this case there is
not a more appropiate place to raise them. Impact is minimized by raising the
Diagnostic only in one pass and minimizing computation in the common case.

## Alternatives considered

The majority of the core feature work was implemented in [this PR](https://github.com/llvm/llvm-project/pull/130356)
which proposed the following solution.

- Introduce a new pass and analysis map for each new piece of data associated with a ResourceBinding
- Emit error Diagnostics live if an invalid state arose
- (Not yet implemented) Backfill `HasCounter` on `TypeInfo` during a later pass

This solution was costly in both perforamance and architecture. It was also
misaligned with other pass infrastructure. Over several round of reviews the PR
require significant changes which ultimatly highlighted the underlying issues.

One coined and reframed as a "Resource Instance Proble", the best solution was clear.

## Acknowledgments

Helena Kotas
Justin Bogner
