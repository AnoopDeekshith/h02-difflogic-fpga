# Step 4.15 independent post-run review (layer-targeted switching penalty)

Reviewer: independent verification sub-agent, Nov 19, 2026.
Scope: frozen plan `docs/experiments/layer-targeting-v1.json` (commit `cfd0c02`,
code `293e450`), evidence `runs/step4.15-targeting.v7r6ms06/` and its single
confirmation attempt `confirm.i235hcd1/`. No tracked file was edited; scratch is
in `runs/step4.15-review.independent/` (`recompute.py`, `recompute.json`,
`spot_mapped.py`, `spot_mapped.json`, three fresh `measure_*` folders).
No test data were loaded.

**Verdict: no BLOCKING finding. The reported numbers, T*/U* selection and
the TARGETING_NOT_SHOWN outcome reproduce exactly.** Three non-blocking wording
points follow.

## 1. Provenance

| Check | Result |
|---|---|
| `plan.json` git_head | `cfd0c028…` = commit `cfd0c02`; written 23:44:49, the commit's own timestamp, before the first training (`seed_1_control` metrics 23:45:04) |
| Policy hash | `f93bf27f…` = working file = `git show cfd0c02:` blob |
| 14 source hashes | all equal the working files and the `cfd0c02` blobs |
| Clean tree | enforced: `git_state()` raises on any tracked modification (see N2) |
| Compatibility gate | seed 1-4 controls and U 0.3 `model.json` are **byte-identical** to the step 4.5 archives, and their hashes equal those in `hardware-switching-stop-rule-v3.json` (8/8) |
| 4.13 reproduction | seed-1 control / U 0.3 M1 = **384,982 / 372,638**; M2 1,061,277 / 1,019,592 equals `docs/results/step-4.13-screening-probe.json` |
| Test data | every run has `test_evaluated: false`, `defer_test: true`, no `*test*` files; `probe.check_run` (manifest/file hashes, seed, lambda, batch mode) passes for all 28 runs |
| Layer weights | `metrics.args.act_layer_weights` equals the profile for every run (`null` for U/control); lambda, seed, split seed 0, 60 epochs, batch mode all match |
| Validation data | one `(x_validation_bits, y_validation)` hash pair across all 28 runs |

## 2. Independent recomputation

`recompute.py` uses its own NumPy gate evaluation (`out=(id>>(3-(2a+b)))&1`,
layers wired by `ia`/`ib`, contiguous 100-gate GroupSum, first-max argmax) and
does not import `dlgn`.

- **Accuracy:** recomputed classes equal `validation_classes.npy` and scores
  equal `validation_scores.npy` for all 28 models; correct counts equal every
  reported `correct`.
- **Logical changes:** adjacent-image settled changes over all 4,000 gates equal
  every reported `logical_changes` (e.g. seed-1 control 379,602).
- **Drops / eligibility / R:** drop_pp, integer eligibility
  `(c_ctrl - c)*100 <= 270`, R_M1, R_M2 and R_logical agree with every row to
  <=1e-12. Zero discrepancies.
- **Discovery grid:** exactly 15 candidates (5 profiles x {0.1, 0.2, 0.3}) plus
  control; U 0.2 is the pre-run review N1 fix, and the grid is otherwise the
  frozen one. Recomputed T* = **RAMP 0.3** (M1 375,707, R_M1 2.41%, 246/270),
  U* = **U 0.2** (R_M1 2.64%, 247/270). No M1 ties, so tie rules were not used.
- **Confirmation (recomputed):**

| Seed | RAMP 0.3 drop | eligible | R_M1 T* | R_M1 U 0.2 (drop) | >=2% | beats comparator | pass |
|---|---:|---|---:|---:|---|---|---|
| 2 | 1.48 pp | no | 2.32% | 2.11% (1.48 pp) | yes | yes | **no** |
| 3 | 0.37 pp | yes | 3.49% | 2.25% (0.37 pp) | yes | yes | yes |
| 4 | 2.59 pp | no | 2.29% | 3.03% (0.00 pp) | yes | **no** | **no** |

  Outcome **TARGETING_NOT_SHOWN**; means R_M1 2.7004% (T*) vs 2.4608%
  (comparator), T* mean drop 1.4815 pp, all identical to `confirmation.json`.
- **Mapped M1 spot checks** (fresh `probe.capture_model` reruns in scratch, same
  v3 window): seed-3 RAMP 0.3 **374,393 / 1,028,813**, seed-4 U 0.2
  **370,170 / 1,011,810**, seed-1 L4 0.3 **381,819 / 1,052,976**: exact equality
  with the archive, with identical LUT4 counts and byte-identical `mapped.json`,
  `net-ledger.json`, `events.csv` and `dlgn_top.sv`. These reruns use the project
  capture/counting code, so they establish determinism, not a second counting
  algorithm (that code was reviewed in step 4.13). All 28 archived measure
  folders show RTL and mapped `PASS: 270/270` and LUT4 counts matching `mapped.json`.

## 3. Methodology

- **Plan followed.** Only one attempt folder exists (`runs/step4.15-targeting.v7r6ms06`),
  with one confirmation subfolder (`confirm.i235hcd1`); no failed or retry
  folders, no error/traceback text in any of the 28 training logs. The
  confirmation trained exactly control, U 0.3, U* (U 0.2) and T* (RAMP 0.3)
  per seed. No lambda was added after discovery, no accuracy relaxation.
- **Conclusion bounded correctly.** NOT_SHOWN follows from two independent
  failures (eligibility on seeds 2 and 4; comparator win on seed 4). It is a
  "not shown under this rule", not evidence that targeting cannot help.

### NON-BLOCKING

**N1. Comparator eligibility and the means.** The outcome rule conditions on
T* eligibility only; U 0.2 is itself ineligible on seed 2 (1.48 pp), so the
seed-2 "beats comparator" comparison is between two ineligible models. The
mean R_M1 gap (2.70% vs 2.46%) mixes ineligible models, is driven by seed 3
(3.49 vs 2.25), and comes with a larger mean accuracy cost (RAMP 1.48 pp vs
U 0.2 0.62 pp). Do not describe it as "targeting slightly better"; report it
with both drops, as the policy's descriptive section requires.

**N2. Clean-tree record.** The policy says `plan.json` "records an empty git
status"; it records only `git_head`. The runner refuses to start on a dirty
tracked tree, so the condition held, but the evidence is the code path, not a
recorded field. Word the walkthrough accordingly.

**N3. The layer-4 explanation is a hypothesis, not a finding.** Data
(seed 1, own NumPy evaluation):

- L4 profile (4x per-gate weight on layer 4) cuts layer-4 changes only
  0.7-1.5% (lambda 0.1-0.3); uniform 0.3 cuts layer 4 by 3.4-5.2% vs layer 1 by
  27-28% across seeds 1-4.
- Layer-4 gates did not become constant: 3 (control) vs 3, 3, 4 (L4 0.1/0.2/0.3);
  uniform 0.3 gives 28-37.
- Layer-4 mean hard 2p(1-p): control 0.4158, L4 0.3 0.4096, U 0.3 0.4008.
  Class selectivity is unchanged: own-class firing 0.785 vs 0.778, other-class
  0.359 vs 0.355.

This supports "layer-4 switching resists the penalty". It does not establish
"because it carries class votes". A perfectly class-selective voter (p about 0.1,
random order) would switch about 2(0.1)(0.9) = 0.18 per pair. That is well below
the observed 0.41 and also better for classification. So the floor imposed by
voting is not binding. Equally consistent alternatives include: a weak
penalty gradient at layer 4 relative to cross-entropy at tau 10, the soft/hard
gap, and the limited reach of 2-input gates without upstream change. State the
mechanism as unestablished.

### NOTES

- **Mapped/logical transfer is not constant.** R_M1/R_logical: U 0.11-0.23
  (nine models), RAMP 0.09-0.28, M23 0.23-0.24 (0.1: -0.08, R_M1 -0.37% with
  +29 LUT4), L34 0.20-0.34, but L4 0.99, 2.93, 1.11. About 0.2 holds for
  profiles dominated by early-layer reductions. For L4 the logical denominators
  are tiny (0.35-0.74%) and per-model synthesis differences (LUT4 -9 to -26)
  dominate. For example, L4 0.2 has R_M1 1.01% from 0.35% logical. Layer-4
  changes also feed the score adders directly, so a higher leverage per change
  is plausible but not separated from synthesis noise here (one synthesis per
  model).
- Discovery on seed 1 reuses the 4.13 seed, as the policy states. Confirmation
  seeds 2-4 are the evidence, and three seeds are a small sample.
- Zero-delay mapped standalone core only: no routing, glitches, power or energy.
- Plan `followup` stands: any carry-over to 4.14 needs a v4 amendment, and
  seeds 1-4 are no longer independent for it.
