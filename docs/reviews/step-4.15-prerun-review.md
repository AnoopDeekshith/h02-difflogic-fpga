# Step 4.15 pre-run independent review

Date: November 18, 2026. Scope: uncommitted 4.15 code, tests and frozen plan,
reviewed **before** any 4.15 training or mapped measurement. The reviewer did
not train, export, synthesize or simulate; only reading and `pytest`.

Reviewed: `dlgn/model.py` (`activity_penalty(mode, layer_weights)`),
`scripts/train.py` (`--act-layer-weights`), `scripts/run_layer_targeting.py`,
`tests/test_layer_weighted_penalty.py`, `tests/test_layer_targeting_rules.py`,
`docs/experiments/layer-targeting-v1.json`,
`docs/discussions/2026-11-18-layer-targeted-penalty.md`, checklist row 4.15,
and the reused `scripts/probe_mapped_switching.py` (`capture_model`,
`load_policy`, `reduction`, `check_run`).

## Checks performed

- Full suite: `.venv/bin/python -m pytest tests -q` -> **325 passed in 16.43 s**, no skips.
- Backward compatibility confirmed independently from the scratch retrains:
  `compat/control/model.json` sha256 `f4cf5d74...a4fe105` and
  `compat/penalty/model.json` `bff429b7...1491f2` equal
  `runs/step4.5-seeds.vyq2h2nf/seed_1_{control,penalty}/model.json` and the
  v3 stop-rule hashes. Their `metrics.json` args show `act_layer_weights: null`,
  `defer_test: true`.
- Penalty formula: `sum_l w_l * mean_l(2p(1-p)) / sum_l w_l` with batch-mean p,
  as documented. Default (`None`) path is literally the old
  `torch.cat(terms).mean()`; equal weights equal the global mean only because
  all layers have equal width (tested and noted in the test name).
- CLI: rejects wrong length, non-numeric, non-finite, negative, zero-sum, and
  weights with `--act-weight 0`. Stored as a float list in `metrics.args`.
- Eligibility `(control - correct)*100 <= n` is the exact 1 pp rule
  (2/270 pass, 3/270 fail). Selection key (M1, -correct, lambda, profile order)
  matches the policy; U rows cannot become T*. Outcome rule matches the policy
  (unrounded `>= 0.02`, strict `>` comparator, empty -> NOT_SHOWN).
- Labels/folders: `seed_{s}_{profile}_{lam}` and `measure_seed_{s}_{label}`
  are unique within and across phases; the confirm `configs` set de-duplicates
  U* == U 0.3; T* and comparator can never be the same config (different
  profiles). Lambda float equality (`0.3` from JSON vs literal) is safe.
- `capture_model` uses the policy only for the window definition string; the
  hash-checked v3 policy is loaded via `probe.load_policy`. Validation images only.
- `default=str`: every value currently written is a native int/float/bool/str/
  list/dict (`correct_count` casts to `int`, means use `float`), so nothing is
  hidden today.

## Findings

### BLOCKING (procedural, trivial)

**B1. The frozen plan and code are uncommitted.** `layer-targeting-v1.json`
has no git history, and `plan.json` records only file hashes. Prior steps
committed each freeze before measurement; do the same here (commit policy,
runner, model/train changes, tests and this review) before `discover`, and
record `git rev-parse HEAD` / a clean `git status --porcelain` in `plan.json`.

### NON-BLOCKING (recommend fixing before the freeze; cheap)

**N1. Comparator may be weak, so TARGETING_BETTER could mean "stronger
penalty beats weaker penalty".** On seed 1, U 0.3 is already ineligible
(245 vs 248, 1.11 pp), so U* is likely U 0.1 (if eligible). T* at lambda 0.3
then only needs to beat U 0.1's R_M1 on each seed. Because the uniform frontier
between 0.1 and 0.3 is unexplored, a win would not show targeting beats uniform
*at matched accuracy*. Options (pick one before running): (a) add uniform
lambda 0.2 (and optionally 0.15) to the discovery grid for U only (about
40 s per model); or (b) keep the grid but narrow the frozen claim wording to
"beats the best eligible uniform configuration from the {0.1, 0.3} grid", and
always report the comparator's per-seed accuracy drop alongside.

**N2. Normalization fairness should be stated, not implied.** Normalization
makes every profile a convex combination of layer means (same scale and
maximum, 0.5 lambda), not the same per-gate pressure. Effective per-layer-mean
coefficients: uniform 0.25 lambda each; L4 lambda on layer 4 (4x); L34/M23
0.5 lambda on two layers (2x); RAMP 0.1/0.2/0.3/0.4 lambda (layer 4 1.6x).
This is acceptable because selection is by eligibility and M1, with lambda as a
knob, but add this table to the policy `limits` or the walkthrough.

**N3. Failure/retry handling is not frozen and confirm cannot retry.** A failed
confirm leaves `confirmation.json` (blocks rerun) and partial `seed_N_*`
folders (`train.py` and `capture_model` reject existing folders). A failed
discovery can be rerun into a fresh `mkdtemp` folder silently. Freeze a rule:
failed attempts are retained and reported; only implementation failures (not
results) justify a retry; confirm writes into a fresh attempt subfolder
(e.g. `confirm.XXXX/`) so a retry does not overwrite or require deletion.

**N4. Training provenance is not rebound before measurement.** `build()` trusts
the subprocess. Call `probe.check_run(run, lam, seed)` (manifest hashes,
`defer_test`, no `x_test_bits.npy`, seed, lambda, batch mode) and additionally
assert `metrics['args']['act_layer_weights'] == weights`.

**N5. State the 4.14 consequence now.** The discussion says the supported
penalty is carried into 4.14, but v3 freezes U 0.3 model hashes for seeds 0-4.
Using T* in 4.14 needs a v4 amendment, and seeds 1-4 would already have been
used for T* discovery/confirmation, so the routed pilot would not be
independent seed evidence for T*. Also, 4.15 measures zero-delay mapped M1 for
seed 2-4 U 0.3 models before 4.14; v3 is already frozen, so this is not a
violation, but record it.

### NOTES

- **Post-hoc / multiple comparisons.** Eight targeted candidates on seed 1 give
  a winner's-curse risk; it is properly contained by confirming one T* on seeds
  2-4 with an all-seeds rule. Seed-1 discovery is acceptable given the stated
  limit. Seeds 2-4 controls/U 0.3 accuracies are known from 4.5 (U 0.3 drops
  6, 0 and 7 images), so eligibility on every seed is likely the binding
  condition; report the three conditions separately per seed so a NOT_SHOWN is
  interpretable. Three seeds are a small sample, as the policy says.
- **M1 zero-delay selection** is appropriate for a screening step consistent
  with 4.12/4.13. It excludes glitches (step 3.9: about 1.7 extra per settled
  change) and each model is a different netlist from one synthesis run; the
  routed, glitch-inclusive check remains 4.14.
- **Determinism cross-check:** the retrained seed-1 control/U 0.3 should
  reproduce the 4.13 M1 values (384,982 / 372,638); asserting this is cheap.
- `activity_penalty` validates non-negativity but not finiteness (CLI does);
  add `math.isfinite` for direct callers.
- `history[].activity_term` holds the weighted value for targeted runs; label it
  in the walkthrough.
- Means are computed for R_M1 (target, comparator) and target drop only; the
  policy's descriptive R_M2, logical reduction and LUT4 counts are present per
  model but not averaged. Fine, but compute them in the report.
- `default=str` could hide a future non-serializable value; restrict it to the
  failure path or remove it.
- `train()` timeout 1800 s is ample (4.5 trainings took 13-15 s); a
  `TimeoutExpired` skips writing the log.

## Consistency

Policy, runner, tests, discussion and checklist row 4.15 agree on profiles
(L4, L34, M23, RAMP + U), lambdas {0.1, 0.3}, seed 1 discovery, seeds 2-4
confirmation, the 1 pp integer rule, tie order, comparator fallback (U 0.3),
the 2% / beat-comparator / all-seeds outcome and the "not energy" limit. The
checklist count (66 tasks) is updated in the header sentence.

## Verdict

Code is correct for the frozen plan; no correctness bug found. Commit the
freeze (B1) before running. N1-N5 are cheap and best decided before the freeze
because changing them after discovery would be post hoc.
