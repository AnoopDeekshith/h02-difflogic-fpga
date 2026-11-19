# Step 4.3 independent review

Review date: November 18, 2026 (local time). Scope: the first matched 60-epoch
control/penalty experiment, one model seed and one nonzero lambda. The
independent reviewer previously reviewed the unchanged selection implementation
in [step 4.10](step-4.10-independent-review.md). No training, full regression
suite or FPGA flow was rerun for this experiment review. The inherited model
was used because the requested legacy review aliases are unavailable; no model
change is claimed.

## Artifact and method review

Primary evidence: `runs/step4.3-pair.ixlscii4/`.
Independent audit: `runs/step4.3-review.independent/audit.py` and `result.json`.

Independent audit SHA-256 fingerprints:

- `runs/step4.3-review.independent/audit.py`: `c5d16f6e6b2805663a5b7fe2f80e31c7c308ef6050c2bb3aa95c123c5ea345ab`
- `runs/step4.3-review.independent/result.json`: `5ab3e1edbe4db688738aff17ee24f9cdd95e41e7a66c0c81356a687bc78318b4`

The audit accepts completed-pending-review and independently-verified root states;
it rejects running/failed experiments and does not alter training bundles.
Reproduce the read-only audit from the repository root:

```bash
.venv/bin/python runs/step4.3-review.independent/audit.py
```

The experiment completed before the verdict: root status is
`completed_pending_independent_review`. Its recorded plan and selection hashes
match the files. The plan predates the recorded results and specifies lambda
0 and 0.1, 60 epochs, digits, four layers × 1,000 gates, tau 10, batch size 100,
Adam learning rate 0.01, CPU, model seed 0 and split seed 0. OMP/MKL thread
limits of one are recorded in the launch plan. Both commands defer test and
use batch-mean activity. The only experimental setting varied is lambda;
output paths necessarily differ.

The audit independently checked:

- All eight archived executable source files match the prewritten plan, current
  source and both sealed run manifests. The copied frozen policy matches the
  planned hash and each run's archived policy.
- Regenerated train/validation indices, exact data/label identities and archived
  validation order match for both runs: 1,077 training and 270 validation images.
- Every archived run artifact passes its manifest check. Test metric fields are
  null, `test_evaluated` is false, and neither run contains test artifacts.
  Logs explicitly record deferred evaluation; loading the dataset/test size is
  separate from test inference.
- Each checkpoint reports completed epoch 60 and the planned configuration.
  Every Adam parameter state records **660 steps**, consistent with
  `60 × ceil(1077 / 100)`. All checkpoint connections and selected discrete
  gates match `model.json`. Checkpoint soft/hard validation accuracy reproduces.
  A separate direct check also confirms the final saved CPU RNG states match;
  the unchanged trainer uses the same seeded shuffle mechanism for both runs.
- Logs and metric history contain epochs 1, 10, 20, 30, 40, 50 and 60.
  Both use the final epoch; no earlier checkpoint was substituted.
- A separate scalar truth-table implementation, independent of `dlgn.hard`,
  matches **every integer score and class on all 270 images** for each run.
  Its strict first-maximum rule preserves lowest-index ties. Scalar adjacent
  gate-state comparisons reproduce each exact change total.
- Validation selection reproduces from the frozen rule and sealed runs.
  All four pre-recorded historical baseline hashes are unchanged:
  `model.json`, `metrics.json`, `x_test_bits.npy` and `y_test.npy` under
  `runs/digits_w1000`.

## Verified result

| Model | Hard validation recognition | Settled changes | Opportunities | Rate |
|---|---:|---:|---:|---:|
| Matched control, lambda 0 | 249/270 = 92.2222% | 373,910 | 1,076,000 | 0.3475000000 |
| Penalty, lambda 0.1 | 245/270 = 90.7407% | 346,963 | 1,076,000 | 0.3224563197 |

The penalty has **26,947 fewer settled changes (7.2068% relative reduction)**
in the same saved validation order. It loses four correct images, or
**1.48148 percentage points**. That exceeds the frozen one-point allowance;
the penalty is ineligible and the selector correctly keeps the control.
The experiment itself is valid and complete even though this candidate fails
the acceptance rule. Its negative selection result and provenance are retained.

No unexpected execution or audit failure occurred: expected versus actual
behavior agreed, including rejection of the penalty candidate by the accuracy
budget. There is no unresolved failure root cause or production fix to report.
The previously reviewed step 4.10 regression contracts and this independent
read-only audit provide prevention against silently changing the comparison or
misreporting the selected model.

## Bounded research assessment

This verifies the matched software experiment and its reported validation
outputs/counts. A batch-mean soft-output term is a training surrogate; measured
hard learned-gate transitions are an unweighted settled logical proxy. The
7.2068% figure applies only to that proxy for this seed and sequence. It is not
mapped-net switching, a glitch reduction, electrical power or energy evidence.
No new RTL equivalence, fit, resource, timing or hardware activity result was
produced. The historical 93.56% test result uses a different protocol and is not
the control here. No new test result is reported.

One penalty strength and one model seed cannot establish a useful tradeoff,
repeatability or novelty. The frozen accuracy allowance remains a declared
working tolerance, not a professor mandate. Further strengths and repeated seeds
belong to steps 4.4 and 4.5. Final test evaluation and hardware checks remain
separate; the historical digits test was already inspected.

## Documentation review

Tracked numerical summary reviewed:
[step-4.3-initial-penalty-experiment.json](../results/step-4.3-initial-penalty-experiment.json).
Its values, comparison arithmetic and negative conclusion agree with the
independently audited artifacts. Final source, primary-evidence, baseline and
independent-audit fingerprints were rechecked after the summary's verification
block was added; all pass.

**PASS: no blocking finding.** The walkthrough, learning index, checklist and
project-context updates correctly preserve the failed accuracy-budget decision,
software-only measurement scope, one-seed limit and prior 285-test attribution.
No executable code changed for this experiment, and no redundant suite or
training run was required. Step 4.1 remains partial with updated evidence;
no general benefit or energy correlation is claimed.

The main agent may mechanically change pending-review wording to independently
verified status, mark step 4.3 complete, synchronize totals to **32 complete /
9 partial / 20 pending**, and set the experiment root status to
`independently_verified`. These changes record this completed review and do not
change the raw training results, plan, frozen policy or selection. No production
correction or further technical recheck is required for step 4.3.
