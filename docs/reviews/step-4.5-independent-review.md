# Step 4.5 independent review

Review date: November 18, 2026 (local time). Scope: the fixed lambda-0.3
repeated-seed software experiment, its paired methodology and descriptive
aggregation. Prior reviews establish the unchanged training/selection contracts:
[step 4.10](step-4.10-independent-review.md),
[step 4.3](step-4.3-independent-review.md) and
[step 4.4](step-4.4-independent-review.md).
No training, full regression suite, test inference or FPGA flow was rerun.

## Planning and method

Primary evidence: `runs/step4.5-seeds.vyq2h2nf/`.
The prewritten plan fixes lambda **0.3**, previously selected using seed 0 in
step 4.4, against lambda-zero controls for new model seeds **1, 2, 3 and 4**.
Eight new runs are distinguished from the explicitly reused seed-0 control and
lambda-0.3 discovery models. The source, policy, reused-model and baseline
fingerprints were recorded before the new runs. The root plan fingerprint
matches; its filesystem timestamp precedes the first new protocol archive.
This supports the recorded execution chronology, not a claim of an external
preregistration or an independently untouched validation dataset.

Each pair uses digits, four layers of 1,000 gates, tau 10, 60 final epochs,
batch size 100, Adam with learning rate 0.01, CPU and recorded one-thread
OMP/MKL settings. The model seed varies connection topology, initial weights and
minibatch shuffle together. These are matched within each pair. Split seed 0,
1,077 training images, 270 validation images and exact validation order are fixed
across every run. Lambda is not retuned for the new seeds. The same frozen
one-percentage-point allowance remains a working tolerance, not a professor
requirement or a statistically derived threshold.

The predeclared consistency rule requires **all four new pairs** to reduce
settled learned-gate changes strictly while staying within that accuracy
allowance. This is a conservative descriptive rule, not a significance test.
The primary aggregation excludes discovery seed 0; the secondary aggregation
includes it and is selection-informed. Every planned pair is retained. A failing
accuracy result cannot be dropped or replaced by reporting only the best seed.
The same validation examples helped select lambda at seed 0, so even the new-seed
cohort tests sensitivity to model randomness on that fixed data; it is not an
independent generalization evaluation.

## Independent artifact audit

The root status was `completed_pending_independent_review` during the completed
audit. Reproduce from the repository root:

```bash
.venv/bin/python runs/step4.5-review.independent/audit.py
.venv/bin/python runs/step4.5-review.independent/summary_audit.py
```

The first command accepts completed-pending-review or independently-verified
root status, rejects unfinished/failed roots, and writes only reviewer evidence.
The second checks the tracked numerical summary against that independent result.
No production or training artifact was edited by this reviewer.

Independent evidence fingerprints:

- `runs/step4.5-review.independent/audit.py`:
  `1be3fa0bd199ddb2029c2bcd13b4d6f6765c0789814397d632e89ce2d5ef7659`
- `runs/step4.5-review.independent/result.json`:
  `84f1df53d4931b424c5823257229323c466785c8c4090d52921687d0ac8cb42e`

All ten manifests and saved artifacts pass integrity checks. The eight source
snapshots agree with current code and each sealed run. Frozen policies, software
versions, regenerated train/validation split indices, data identities and exact
validation order agree across all ten models. Both reused seed-0 model/manifest
fingerprints and the four historical baseline fingerprints are unchanged.
Logs and metric histories contain the planned final epoch. All checkpoints
complete **60 epochs**, with **660 Adam steps per parameter**
(`60 × ceil(1077 / 100)`), and checkpoint connections/discrete gates match the
saved hard model. Soft and hard validation recognition recompute correctly.
Test fields remain null, test evaluation is false, and no test export exists.
The loader returning test arrays is distinct from performing test inference.

A separate scalar truth-table oracle, independent of the NumPy hard evaluator,
checks **2,700 image computations**: every integer class score, lowest-index
maximum-class decision and exact adjacent learned-gate transition count for
270 images in each of ten models. Each denominator is
**1,076,000 = 4,000 gates × 269 adjacent-image pairs**. Checkpoint PyTorch hard
scores round to those same exact integers and agree within the expected division
rounding; the scalar/NumPy integer comparisons themselves use exact equality.

Reconstructed seeded initialization gives matching initial weights and
connections within each pair; the five seed initializations/topologies differ.
Every saved final RNG state matches its pair and an independent execution of
exactly 60 seeded `randperm(1077)` calls, consistent with the reviewed trainer's
shuffle mechanism. Initial weights and per-epoch permutations were not separately
archived: their matching is supported by deterministic reconstruction, unchanged
source and final RNG evidence, not by a claim of saved initial checkpoints.

All four saved new-seed selections reproduce. Independent eligibility uses the
integer condition `100 × (control_correct − penalty_correct) <= 270`, avoiding
floating-point ambiguity at the one-point threshold. Thus a loss of two images
is allowed (0.74074 pp), whereas a loss of three is not (1.11111 pp). Seed-0 pair
selection is also reconstructed without relabeling its reused evidence as new.

## Verified result and aggregation

| Seed | Origin | Control correct / 270 | Penalty correct / 270 | Control changes | Penalty changes | Reduction | Accuracy loss | Joint pass |
|---:|---|---:|---:|---:|---:|---:|---:|---|
| 0 | Reused discovery | 249 | 247 | 373,910 | 309,698 | 17.1731% | 0.7407 pp | Yes |
| 1 | New | 248 | 245 | 379,602 | 318,730 | 16.0357% | 1.1111 pp | No |
| 2 | New | 253 | 247 | 377,280 | 314,169 | 16.7279% | 2.2222 pp | No |
| 3 | New | 248 | 248 | 376,560 | 315,359 | 16.2527% | 0.0000 pp | Yes |
| 4 | New | 249 | 242 | 379,777 | 312,011 | 17.8436% | 2.5926 pp | No |

The primary four-new-seed aggregate gives **16.71498% mean relative switching
reduction**, sample SD **0.80604 percentage points of that percentage metric**,
range **16.03574–17.84363%**. Mean accuracy loss is **1.48148 pp**, sample SD
**1.17121 pp**, range **0–2.59259 pp**. All four lower switching, but only
**one of four** meets both conditions. The declared all-four consistency rule
therefore **fails**. The selectors retain the control for seeds 1, 2 and 4 and
accept the penalty for seed 3; that does not authorize discarding failed pairs
from the experiment or promoting seed 3 as a generally superior model.

For the four new seeds, mean control accuracy is **92.40741%** (sample SD
**0.88166 pp**) and mean penalty accuracy is **90.92593%** (sample SD
**0.97991 pp**). Mean rates are **0.3515843401** versus **0.2928134294**, with
sample SDs **0.0015123917** and **0.0026093223**. Separately, pooled changes
fall from **1,513,219 to 1,260,269**, a **16.71602%** reduction. Pooling weights
pairs by their control counts; it is not identical to the unweighted mean of
per-pair relative reductions.

The explicitly secondary five-seed aggregate gives mean reduction
**16.80661%**, sample SD **0.72750**, and mean accuracy loss **1.33333 pp**,
sample SD **1.06703 pp**. Two of five pass both conditions. Pooled changes are
**1,887,129 versus 1,569,967**, a **16.80659%** reduction. Including the discovery
pair does not turn this into a confirmatory five-seed study.

The summary audit independently checks every row, both aggregates' means,
sample SDs (`ddof=1`), ranges, inclusion/counts, pooled totals, selection decisions
and provenance fingerprints. Raw integers and decisions are exact. A zero-relative,
`1e-12` absolute tolerance is used only for alternate floating-point report
arithmetic; no eligibility or measurement tolerance was relaxed.

No unexpected execution or audit failure occurred. Accuracy-budget failures
are legitimate experimental outcomes, retained with provenance; they are not
software failures requiring a debug fix. Expected versus actual artifact,
checkpoint, scalar and aggregation behavior agreed. No uncertain execution
root cause or production correction remains.

## Bounded research assessment

This verifies the matched software experiment and its reproducible integer
outputs/counts. It supports a consistent reduction of the **settled logical
switching proxy in these four new seeds**, alongside an **inconsistent accuracy
tradeoff under the frozen allowance**. It does not establish an acceptable
optimization across seeds. The soft batch-mean `2p(1−p)` term remains a surrogate;
the hard learned-gate count is unweighted and sequence-dependent.

All ten model evaluations use the **same 270 distinct validation images**.
There are 2,700 model-image computations, not 2,700 independent examples or
five independent datasets. The sample SD describes seed variation conditional
on this fixed dataset/protocol, not dataset sampling uncertainty. Four new seeds
do not justify a population acceptance probability, significance or broad
repeatability claim. The historical digits test was already inspected, and no
new test evaluation was performed here.

There is no new RTL equivalence, device fit, timing, mapped/glitch activity,
power estimation or electrical energy result. The historical baseline has a
different training protocol and is not a matched control for this comparison.
Lower unweighted settled transitions cannot establish lower power or energy,
and novelty remains unverified. Hardware/energy follow-up and broader datasets
remain separate research work. The deferred VCD parser cleanup is not executed
by this software experiment.

## Documentation verdict

Numerical summary reviewed:
[step-4.5-repeated-seeds.json](../results/step-4.5-repeated-seeds.json).
Its five rows and both aggregates agree with the independent audit. Reviewed the
walkthrough, project README, learning index, checklist and project context.
They preserve all accuracy failures, distinguish discovery from new repeats,
retain the primary all-four failure, and keep step 4.6 and hardware/energy work
pending. A weaker fixed-lambda follow-up is described as future work requiring
a new plan; no follow-up result or best-seed promotion is claimed.

The archived summarizer's arithmetic was reviewed. Its default prints without
writing, and its optional output uses exclusive file creation. The output-hygiene
change leaves the checked numerical aggregates unchanged. Both summary copies
are identical, and all four verifier-file fingerprints in their verification
block pass. Source, baseline and reused-model hashes were checked again; local
documentation links resolve.

Auxiliary evidence fingerprints:

- `runs/step4.5-review.independent/summary_audit.py`:
  `08441a577ce5daf477e641d9a979f16fb657f0e6718839e0e1efff32cf8c8daa`
- `runs/step4.5-review.independent/summary-audit-result.json`:
  `f321d09b040e3a9b989c95a556877ddc079acfc385ce185d429ccbd8d71e3ef4`

The auxiliary result fingerprints the numerical/provenance payload excluding
status and verification metadata, avoiding a circular hash when its own hash is
added to that metadata. Integer evidence and all aggregation values are checked.

**PASS: no blocking finding.** This verdict approves the experiment's execution,
methodology, reported negative consistency result and documentation; it does
not approve lambda 0.3 as a robust optimization. The main agent may mechanically
mark step 4.5 independently verified, set the root status to
`independently_verified`, synchronize totals to **34 complete / 9 partial /
18 pending**, and update status/review fingerprints in both summaries. Those
status changes do not require another technical audit. No training, extra
full-suite run or production correction is needed.
