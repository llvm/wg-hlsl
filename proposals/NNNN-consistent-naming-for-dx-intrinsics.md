<!-- {% raw %} -->

# Consistent Naming for DX Intrinsics

* Proposal: [NNNN](NNNN-consistent-naming-for-dx-intrinsics.md)
* Author(s): [Justin Bogner](https://github.com/bogner)
* Status: **Design In Progress**

## Introduction

LLVM's directx target intrinsics all fall under the llvm.dx.* name, but we have
some inconsistency on how the names are constructed from there. Notably, some
of the resource ops have camelCase in their names right now, which is
inconsistent with general LLVM style.

- We have ops with one word names. This covers various basic operations like
  `llvm.dx.all`, `llvm.dx.frac`, or `llvm.dx.isinf`. These are straightforward,
  and generally pretty obvious.
- We have ops that are cordoned off into namespaces, like
  `llvm.dx.wave.getlaneindex` and `llvm.dx.wave.is.first.lane`. We should
  probably be consistent about whether we separate words or not on the op name
  here.
- We have ops with multiple word names separated by dots, like
  `llvm.dx.thread.id` and `llvm.dx.flattened.thread.id.in.group`.

We should adopt a consistent policy around how to name the DX intrinsics and
stick to it.

## Proposed solution

- Avoid camel case
- Try to use names that are obvious without arbitrary spaces.
  `llvm.dx.wave.getlaneindex`, not `llvm.dx.wave.is.first.lane`
- Namespace handle ops under "resource": `llvm.dx.resource.frombinding`,
  `llvm.dx.resource.fromheap`. Include `llvm.dx.resource.pointer` or
  `llvm.dx.resource.access` here for getting a pointer in a namespace for
  resources.
- Namespace other resource ops with the verb and then specialize with the type:
  `llvm.dx.store.typedbuffer`, `llvm.dx.load.texture`, `llvm.dx.sample`,
  `llvm.dx.sample.bias`, `llvm.dx.getdimensions.typedbuffer`, `llvm.dx.gather`,
  `llvm.dx.getsampleposition.Texture2DMS`
- Use other namespaces where it makes sense, like `wave`, `quad`, and
  `rayquery`.

## Detailed design

Applying these naming conventions to a number of ops, we can get a taste for
how the naming convention will work. What follows are a large number of
examples and some open questions around a few of them.

#### Thread and Group IDs
```llvm
llvm.dx.threadid ; (ThreadId)
llvm.dx.groupid ; (GroupId)
llvm.dx.threadidingroup ; (ThreadIdInGroup)
llvm.dx.flattenedthreadidingroup ; (FlattenedThreadIdInGroup)
```

Open questions:
- Is "flattenedthreadidingroup" too unwieldy?

#### Resource ops
```llvm
llvm.dx.resource.handlefrombinding ; (CreateHandleFromBinding)
llvm.dx.resource.handlefromheap ; (CreateHandleFromHeap)
llvm.dx.resource.annotatehandle ; (AnnotateHandle)
llvm.dx.resource.load.rawbuffer ; (RawBufferLoad)
llvm.dx.resource.load.typedbuffer ; (BufferLoad)
llvm.dx.resource.load.texture ; (TextureLoad)
llvm.dx.resource.load.cbufferrow ; (CBufferLoadLegacy)
llvm.dx.resource.load.cbuffer ; (CBufferLoad)
llvm.dx.resource.store.rawbuffer ; (RawBufferStore)
llvm.dx.resource.store.typedbuffer ; (BufferStore)
llvm.dx.resource.store.texture ; (TextureStore)
llvm.dx.resource.store.texturesample ; (TextureStoreSample)
llvm.dx.resource.writesamplerfeedback ; (WriteSamplerFeedback)
llvm.dx.resource.writesamplerfeedbackbias ; (WriteSamplerFeedbackBias)
llvm.dx.resource.writesamplerfeedbacklevel ; (WriteSamplerFeedbackLevel)
llvm.dx.resource.writesamplerfeedbackgrad ; (WriteSamplerFeedbackGrad)
llvm.dx.resource.updatecounter ; (BufferUpdateCounter)
llvm.dx.resource.getdimensions ; (GetDimensions)
llvm.dx.resource.sample ; (Sample)
llvm.dx.resource.samplelevel ; (SampleLevel)
llvm.dx.resource.samplebias ; (SampleBias)
llvm.dx.resource.samplegrad ; (SampleGrad)
llvm.dx.resource.samplecmp ; (SampleCmp)
llvm.dx.resource.samplecmpbias ; (SampleCmpBias)
llvm.dx.resource.samplecmpgrad ; (SampleCmpGrad)
llvm.dx.resource.samplecmplevel ; (SampleCmpLevel)
llvm.dx.resource.samplecmplevelzero ; (SampleCmpLevelZero)
llvm.dx.resource.texturesamplepos ; (Texture2DMSGetSamplePosition)
llvm.dx.resource.gather ; (TextureGather)
llvm.dx.resource.gathercmp ; (TextureGatherCmp)
llvm.dx.resource.gatherraw ; (TextureGatherRaw)
llvm.dx.resource.atomicbinop ; (AtomicBinOp)
llvm.dx.resource.atomiccmpxchg ; (AtomicCompareExchange)

; Intermediate resource op:
llvm.dx.resource.getptr
```

Open questions:
- Should we categorize "BarrierByMemoryHandle" as under resource
  (`llvm.dx.resource.barrier`) or barrier (`llvm.dx.barrier.resource`)?

#### Node ops
```llvm
llvm.dx.node.createoutputhandle ; (CreateNodeOutputHandle)
llvm.dx.node.indexhandle ; (IndexNodeHandle)
llvm.dx.node.annotate ; (AnnotateNodeHandle)
llvm.dx.node.isvalid ; (NodeOutputIsValid)
llvm.dx.node.allocaterecords ; (AllocateNodeOutputRecords)
llvm.dx.node.incrementoutputcount ; (IncrementOutputCount)
```

#### Node Record ops
```llvm
llvm.dx.noderecord.createinputahandle ; (CreateNodeInputRecordHandle)
llvm.dx.noderecord.annotate ; (AnnotateNodeRecordHandle)
llvm.dx.noderecord.getptr ; (GetNodeRecordPtr)
llvm.dx.noderecord.outputcomplete ; (OutputComplete)
llvm.dx.noderecord.getinputrecordcount ; (GetInputRecordCount)
llvm.dx.noderecord.finishedcrossgroupsharing ; (FinishedCrossGroupSharing)
```

Open questions:
- Should we categorize "BarrierByNodeRecordHandle" as under resource
  (`llvm.dx.noderecord.barrier`) or barrier (`llvm.dx.barrier.noderecord`)?

#### Barriers
```llvm
llvm.dx.barrier ; (Barrier)
llvm.dx.barrierbymemorytype ; (BarrierByMemoryType)
```

Open questions:
- Should all barriers live in `dx.barrier.*`, or should we only have "general"
  barriers here?

#### Other
```llvm
llvm.dx.getremainingrecursionlevels ; (GetRemainingRecursionLevels)
```

Open questions:
- Should we nest GetRemainingRecursionLevels under node, as
  `llvm.dx.node.getremainingrecursionlevels`?

#### Signature metadata
```llvm
; siginput: indexing into the input signature metadata
llvm.dx.siginput.load ; (LoadInput)
llvm.dx.siginput.evalsnapped ; (EvalSnapped)
llvm.dx.siginput.evalsampleindex ; (EvalSampleIndex)
llvm.dx.siginput.evalcentroid ; (EvalCentroid)
llvm.dx.siginput.loadoutputcontrolpoint ; (LoadOutputControlPoint)
llvm.dx.siginput.attributeatvertex ; (AttributeAtVertex)

; sigoutput: indexing into the output signature metadata
llvm.dx.sigoutput.store ; (StoreOutput)

; sigpatchconstant: indexing into the patch constant signature metadata
llvm.dx.sigpatchconstant.load ; (LoadPatchConstant)
llvm.dx.sigpatchconstant.store ; (StorePatchConstant)
```

#### Geometry Shader Stream ops
```llvm
llvm.dx.gsstream.emit ; (EmitStream)
llvm.dx.gsstream.cut ; (CutStream)
llvm.dx.gsstream.emitthencut ; (EmitThenCutStream)
```

#### RayQuery ops
```llvm
llvm.dx.rayquery.allocate ; (AllocateRayQuery)
llvm.dx.rayquery.* ; (RayQuery_*)
```

#### Wave ops
```llvm
llvm.dx.wave.isfirstlane ; (WaveIsFirstLane)
llvm.dx.wave.getlaneindex ; (WaveGetLaneIndex)
llvm.dx.wave.getlanecount ; (WaveGetLaneCount)
llvm.dx.wave.any ; (WaveAnyTrue) (note: could map llvm.dx.wave.reduce.or.i1)
llvm.dx.wave.all ; (WaveAllTrue) (note: could map llvm.dx.wave.reduce.and.i1)
llvm.dx.wave.allequal ; (WaveActiveAllEqual)
llvm.dx.wave.ballot ; (WaveActiveBallot)
llvm.dx.wave.readfirst ; (WaveReadLaneFirst)
llvm.dx.wave.readat ; (WaveReadLaneAt)
llvm.dx.wave.reduce.sum ; (WaveActiveOp: sum)
llvm.dx.wave.reduce.product ; (WaveAciveOp: product)
llvm.dx.wave.reduce.smin ; (WaveAciveOp: min, signed)
llvm.dx.wave.reduce.smax ; (WaveAciveOp: max, signed)
llvm.dx.wave.reduce.umin ; (WaveAciveOp: min, unsigned)
llvm.dx.wave.reduce.umax ; (WaveAciveOp: max, unsigned)
llvm.dx.wave.reduce.and ; (WaveActiveBit: and)
llvm.dx.wave.reduce.or ; (WaveActiveBit: or)
llvm.dx.wave.reduce.xor ; (WaveActiveBit: xor)
llvm.dx.wave.bitcount ; (WaveAllBitCount)
llvm.dx.wave.prefixop ; (WavePrefixOp)
llvm.dx.wave.prefixballot ; (WavePrefixBitCount)
llvm.dx.wave.match ; (WaveMatch)
; wavemulti ops take a mask that sub-groups lanes for each operation
llvm.dx.wavemulti.* ; (WaveMultiPrefixOp: sum, and, or, xor, product)
llvm.dx.wavemulti.ballot ; (WaveMultiPrefixBitCount)
```

#### Quad ops
```llvm
llvm.dx.quad.* ; (Quad*)
llvm.dx.quad.readat ; (QuadReadLaneAt)
llvm.dx.quad.readacrossx ; (QuadOp: ReadAcrossX)
llvm.dx.quad.readacrossy ; (QuadOp: ReadAcrossY)
llvm.dx.quad.readacrossdiagonal ; (QuadOp: ReadAcrossDiagnonal)
llvm.dx.quad.vote ; (QuadVote) (could map from llvm.dx.quad.reduce.[and|or].i1)
```

## Acknowledgments

- Thanks to Tex Riddell for surveying the DXIL op names and coming up with the
  scheme used in most of the examples.

<!-- {% endraw %} -->
