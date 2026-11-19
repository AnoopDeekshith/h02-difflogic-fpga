# Step 4.4 independent review

Review date: November 18, 2026 (local time). Scope: a validation-only,
single-seed penalty-strength sweep using unchanged executable code. This
reviewer previously reviewed the implementation in
[step 4.10](step-4.10-independent-review.md) and the reused matched pair in
[step 4.3](step-4.3-independent-review.md). No training, full test suite or FPGA
flow is rerun here. The inherited model is used because the requested legacy
aliases are unavailable; no model change is claimed.

## Planning and provenance

Primary evidence: `runs/step4.4-sweep.zlmbqzyd/`.
The prewritten plan fixes the grid **0, 0.001, 0.003, 0.01, 0.03, 0.1, 0.3, 1**.
Six strengths are new runs; lambda 0 and 0.1 are explicitly reused verified
step 4.3 archives with pre-recorded model, manifest and log fingerprints.
They are not represented as new runs.

The grid was chosen after the known step 4.3 result and before the six new
results. This is disclosed validation-guided development, not a globally blind
preregistration. The existing one-percentage-point control-relative accuracy
budget is unchanged. Every declared grid point must appear in selection,
including rejected candidates; the control remains selectable.

The initial audit found that the plan/status hash, policy hash, all eight
archived/current source fingerprints, reused artifact/log fingerprints and four
historical baseline hashes agree. All commands specify 60 epochs, digits,
width 1,000, depth 4, tau 10, batch size 100, Adam learning rate 0.01, model
seed 0, split seed 0, CPU and batch activity with deferred test evaluation.
The plan records OMP/MKL thread limits of one.

Independent read-only audit: `runs/step4.4-review.independent/audit.py`.
Reproduction command, after the root experiment status is complete:

```bash
.venv/bin/python runs/step4.4-review.independent/audit.py
```

The audit permits completed-pending-review or independently-verified root
status and rejects running/failed experiments. It checks manifests and matched
protocols, regenerated data identities/indices, source/policy archives, final
checkpoints/optimizer states, logs, all validation scores/classes/counts using a
separate scalar truth-table oracle, final RNG states, inclusion of every grid
point, an independent accuracy-floor ranking and preservation of baseline/reused
artifacts. No production file is changed by the reviewer.

## Completed artifact audit

The root experiment status is `completed_pending_independent_review`; its plan
and selection fingerprints agree. The independent audit completed successfully
without training or test inference. It recalculated all eight models, including
the two reused archives, rather than assuming old results were fresh runs.

Independent audit fingerprints:

- `runs/step4.4-review.independent/audit.py`:
  `c8ffaad5e6c72617387b4bef8088f8236a220ce90caff6c49d32fb26cab8bcc2`
- `runs/step4.4-review.independent/result.json`:
  `cfbe9a1b5b63adfa769c59643a373eca89e3e49cdaf93529b8f86812ce0c2eaa`

Every checkpoint is final epoch **60**, with **660 Adam steps** for each
parameter (`60 × ceil(1077 / 100)`). Saved checkpoint connections/discrete gate
choices match the hard model; soft and hard validation accuracy reproduce.
Every saved final CPU RNG state matches, consistent with the unchanged seeded
shuffle mechanism. Logs and history contain the planned final epoch rather than
an earlier preferred checkpoint. No test result fields or test artifacts are
present. Regenerated splits/data labels and all saved validation inputs/order
match. Source snapshots, policies, versions, all manifests and both reused
model/manifest/log records are consistent; the four historical baseline
fingerprints are unchanged.

A separate scalar truth-table oracle matched every one of **2,160 image
computations** (270 × 8): every integer class score, lowest-index class decision
and exact adjacent learned-gate change total. Each denominator is **1,076,000 =
4,000 gates × 269 adjacent-image pairs**.

| Lambda | Origin | Hard correct / 270 | Settled changes | Eligible |
|---:|---|---:|---:|---|
| 0 | Reused verified control | 249 | 373,910 | Yes |
| 0.001 | New | 248 | 374,016 | Yes |
| 0.003 | New | 247 | 373,790 | Yes |
| 0.01 | New | 248 | 373,056 | Yes |
| 0.03 | New | 247 | 366,252 | Yes |
| 0.1 | Reused verified penalty | 245 | 346,963 | No |
| 0.3 | New | 247 | 309,698 | Yes |
| 1 | New | 236 | 215,729 | No |

The independently reconstructed accuracy floor is **91.2222%**; with 270 images,
at least **247 correct** are needed. Independent ranking across every declared
point agrees with the saved selector: **lambda 0.3** has the lowest eligible
settled rate, **0.28782342007434947**. It has **64,212 fewer changes**, a
**17.173116525% relative reduction**, and **two fewer correct images**, a
**0.740740741-percentage-point loss**, relative to this matched control.
Lambda 1 switches still less but fails the unchanged accuracy budget and is
retained in the report. Lower switching is not assumed monotonic with lambda:
for example, lambda 0.001 is slightly worse than the control.

This is an accepted **single-seed validation proxy tradeoff** under the declared
rule. It does not establish a repeated-seed improvement or hardware benefit.
Training and the scalar/checkpoint/selection audit had no unexpected failure.
An extra summary-reporting helper initially required overly strict equality
between two floating-point forms of the same percentage; that helper issue is
recorded below. No production fix or acceptance-rule change was needed.

## Debug record: derived-percentage audit precision

The reviewer applied `engineering:debug` to reproduce, isolate and diagnose an
unexpected assertion in an additional summary-check helper.

- **Expected:** independently calculated derived percentages agree with the
  tracked summary to arithmetic precision, while all integer results and
  eligibility decisions remain exact.
- **Actual:** strict float `==` failed for lambda 0.01's switching reduction.
  `854 / 373910 × 100` produces `0.22839720788425025`, whereas
  `854 × 100 / 373910` produces the recorded `0.22839720788425022`.
  The difference is `2.7755575615628914e-17` percentage points.
- **Exact reproduction:** run
  `.venv/bin/python runs/step4.4-review.independent/rounding-reproduction.py`.
  The intentionally failing script and its original traceback are preserved in
  `rounding-reproduction.py` and `rounding-reproduction.log` in that directory.
- **Root cause:** IEEE floating-point rounding depends on operation order.
  The mathematical rational value is the same; no integer count, score,
  accuracy floor, eligibility flag or selected model differs.
- **Fix:** the independent summary helper uses `math.isclose` with zero relative
  tolerance and `1e-12` absolute tolerance solely for derived percentages.
  All raw integer values, fingerprints, recorded rates, floor and decisions
  still use exact checks. No production or experiment artifact was changed.
- **Verification:**
  `.venv/bin/python runs/step4.4-review.independent/summary_audit.py` passes all
  eight rows, hashes and selected-model checks. The largest difference between
  equivalent derived-percentage calculations is `6.050715484207103e-15`, well
  below the tight arithmetic tolerance.
- **Prevention:** use exact equality for scientific integer evidence and
  decisions; reserve a small explicit absolute tolerance for independently
  reordered floating-point report arithmetic. The cause is established.

## Final documentation verdict

**PASS: no blocking finding.** Rechecked the walkthrough, all eight tracked
summary rows, new-versus-reused origins, comparison arithmetic, selected-model
record, learning index, checklist and project context. Their claims agree with
the independent evidence and retain the planning chronology, rejected points,
provisional single-seed interpretation, previous-suite attribution and lack of
hardware/energy/novelty evidence. The final summary audit and primary/baseline/
reused/independent fingerprints pass. The floating-point helper issue above is
fully explained and preserved; it is not a production defect.

The main agent may mechanically mark step 4.4 independently verified, update the
root status to `independently_verified`, and synchronize checklist totals to
**33 complete / 9 partial / 19 pending**. The audit already accepts that final
root status. No executable change, extra training or full-suite rerun is needed;
no further technical recheck is required for those status updates.

## Bounded research assessment

A validated result here concerns hard-model recognition and unweighted settled
learned-gate transitions on one fixed validation sequence. The batch-mean
soft-output penalty is a training surrogate. Neither quantity includes mapped
capacitance, routing, physical hazards or clock power. This step supplies no
new RTL equivalence, fit, resource, timing, power-estimation, electrical-energy
or novelty evidence. One seed does not establish reproducibility or statistical
general benefit. The historical digits test was already inspected; no new test
evaluation belongs in this selection step.

The pending VCD parser/validator consolidation is a separate hardware-activity
follow-up. The unchanged NumPy-only training/selection path does not execute
that VCD code; the deferred cleanup is not evidence of a new measurement fix.
