# Step 4.10 independent review

Review date: November 18, 2026. Scope: validation-only selection preparation,
not the later meaningful penalty experiment (4.3), sweep or energy comparison.
The independent reviewer read `AGENTS.md`, `CLAUDE.md`, project context and the
checklist. The main agent implemented the production changes; this reviewer
owns the additional regression file and this review. Requested legacy model
aliases are unavailable in this runtime; the inherited model was used, without
claiming a model change.

## Code and methodology

Reviewed `dlgn/experiment.py`, `scripts/train.py`,
`scripts/select_validation_models.py`, `scripts/evaluate_selected_model.py`,
`docs/experiments/validation-selection-v1.json` and the original regression file.
No blocking defect was found in this scope.

- The accuracy tolerance is copied and hashed into each run before the first
  gradient update. One percentage point is a declared experimental choice,
  not a professor requirement or an empirically optimized tolerance.
- Training uses validation for monitoring and saves the final epoch of a fixed
  budget. Deferred mode does not infer on or archive test inputs/labels.
  Loading the dataset and recording its test-set size does not reveal test
  recognition or switching measurements.
- Selection checks matched architecture, model seed, data split/identities,
  budget, optimizer settings, activity mode, software versions and source hashes.
  The lambda-zero control remains selectable. Batch and per-sample penalties
  cannot be silently combined in one matched comparison.
- NumPy recalculates every saved integer score, lowest-index class decision,
  accuracy and adjacent-image gate-change total in the saved validation order.
  The denominator is learned gate count times adjacent-image pairs, excluding
  an invented initial-state transition. The PyTorch hard-score comparison
  allows only a small floating-point rescaling tolerance; NumPy scores themselves
  are saved and compared as exact integers.
- Fresh run/evaluation paths are required; failed attempts retain failed status.
  Manifest checks reject changed or incomplete archived artifacts. Executable
  sources are fingerprinted before training and checked again before sealing.
- The later evaluator verifies the selection again, loads the selected checkpoint
  without optimization and checks checkpoint/hard-model correspondence before
  reporting test scores. It requires the recorded executable source hashes.
  Historical `runs/digits_w1000` is not used as a matched control or overwritten.

## Independent verification

Commands, from the project root:

```bash
.venv/bin/python -m pytest tests/test_validation_selection.py -q
.venv/bin/python -m pytest tests/test_validation_selection_review.py -q
```

Results: **23 passed in 3.36 s** and **7 passed in 4.40 s**, respectively.
No full regression suite, FPGA flow or expensive training was duplicated by
this reviewer. The main agent reports the broader full suite: **285 passed in
19.18 s, no skips** (255 existing + 23 selection + 7 independent cases).

The seven new independent cases check:

1. Fresh NumPy recomputation rejects an incorrect reported validation accuracy,
   even when a writer has recalculated artifact hashes.
2. Every integer score is checked when predicted classes would remain unchanged.
3. Validation-order changes are rejected unless their identity is consistent.
4. Batch activity and the sample ablation cannot be mixed as matched protocols.
5. Duplicate candidates and a nonzero-lambda control are rejected.
6. Post-selection evaluation calls neither training nor optimizer steps and
   cannot overwrite its destination.
7. Evaluation rejects executable source changes before creating output.

These injected invalid inputs were rejected as expected. There was no unexpected
failure requiring a production fix: expected versus actual behavior agreed;
there is no unresolved root cause or corrective patch to report. The regression
cases preserve those contracts against future accidental changes.

## Real-data mechanism check

Independently re-read both complete archives in
`runs/step4.10-preparation.20uuxoj6/`, checked manifests/current executable hashes
and reproduced the saved selection from its frozen policy. Both runs use one
CPU epoch, width 1,000, depth 4 and the same seed/split/budget. Both explicitly
report `test_evaluated: false`.

| Run | Validation recognition | Settled gate changes | Opportunities | Rate |
|---|---:|---:|---:|---:|
| Control | 45/270 | 201,962 | 1,076,000 | 0.18769702602230484 |
| Penalty | 41/270 | 195,210 | 1,076,000 | 0.18142193308550186 |

A separate scalar gate-table oracle, independent of `dlgn.hard`, processed all
270 saved images of each run. Every archived score and class matched; it also
reproduced exactly 201,962 and 195,210 changes. Each denominator is
4,000 gates × 269 adjacent-image pairs.

The penalty model loses 4/270 = **1.48148 percentage points**, beyond the frozen
one-point budget. Selection correctly chooses the control. Low one-epoch
accuracy makes these mechanism checks only; neither training effectiveness nor
an accepted accuracy/switching improvement is established. No real-data test
evaluation was needed to verify preparation; the evaluator is exercised on the
synthetic regression workload.

## Bounded research assessment

Tested correctness covers the software protocol, archive consistency, reference
scores/classes and fixed-order logical counts. Settled unweighted learned-gate
changes are a measurement proxy; the batch-mean IID term is a training surrogate.
Neither accounts for mapped capacitance, clock power, routing or physical
hazards. This step provides no new RTL equivalence, hardware fit/timing,
power-estimator result, electrical energy measurement or evidence of novelty.
Matched longer training, repeated seeds and hardware checks remain necessary.
The historical digits test was inspected previously and remains exploratory.

## Final documentation review

**PASS: no blocking finding.** Rechecked the completed walkthrough, tracked
result JSON, root README, learning index, checklist row and project-context
updates. All reported mechanism values and source/evidence/model/manifest/
selection hashes agree with the archived files. The 285-test total correctly
includes 23 new selection cases and 7 independent cases; the earlier focused
27-test command also contained four existing partition cases.

The documentation distinguishes preparation from a useful trained penalty
result, identifies the arbitrary working accuracy tolerance, preserves the
historical baseline and inspected-test caveat, and makes no new energy or
novelty claim. The final change from pending-review wording to independently
verified status, and the corresponding 31 complete / 9 partial / 21 pending
checklist totals, is an authorized mechanical reflection of this review. No
production corrections or further technical review are required for step 4.10.
