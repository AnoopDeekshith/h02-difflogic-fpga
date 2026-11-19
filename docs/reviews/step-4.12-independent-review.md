# Step 4.12 independent review: hardware-switching stop rule

Reviewer: independent verification sub-agent. Date: November 18, 2026.
Scope is limited to reading files and making small hash/JSON checks. I ran no
export, synthesis, placement, routing or simulation of any model.

## Scope

- Policy: `docs/experiments/hardware-switching-stop-rule-v1.json`
- Walkthrough: `docs/steps/4.12-freeze-the-hardware-stop-rule.md`
- Discussion: `docs/discussions/2026-11-18-small-saving-publication-and-pilot-plan.md`
- Context: `docs/results/step-4.5-repeated-seeds.json`,
  `docs/experiments/validation-selection-v1.json`, steps 3.8 and 3.9
  walkthroughs, checklist rows 3.11 and 4.12–4.14, `AGENTS.md`, `CLAUDE.md`.

## Checks performed

| Check | Command (from repo root) | Result |
|---|---|---|
| Policy hash | `shasum -a 256 docs/experiments/hardware-switching-stop-rule-v1.json` | `9b1c2faa…3458bc`, matches the stated freeze hash |
| Git state | `git status --short` | Policy and walkthrough are **untracked**; checklist modified. `scripts/probe_mapped_switching.py` and `tests/test_probe_mapped_switching.py` are also untracked (written 23:07, after the policy's 23:04 mtime) |
| Hardware artifacts in new-model folders | `find runs/step4.3-pair.* runs/step4.4-sweep.* runs/step4.5-seeds.* runs/*review.independent* runs/step4.10-preparation.* \( -iname '*.sv' -o -iname '*.v' -o -iname '*.hex' -o -iname '*.mem' -o -iname '*.vcd' -o -iname '*.fst' -o -iname '*.asc' -o -iname '*.bin' -o -iname '*.sdf' -o -iname '*.blif' -o -iname '*.vvp' -o -iname '*synth*' -o -iname 'rtl_*' -o -iname 'uart_*' -o -iname 'mapped*' -o -iname 'timed*' \)` | None. File types present: json 131, npy 72, npz 18, pt 18, py 31, log 28 |
| Logs mention hardware tools | `grep -liE 'yosys\|nextpnr\|iverilog\|vvp\|icepack\|synth_ice40'` over those 28 logs | No matches (training/selection/audit logs only) |
| Hardware files anywhere newer than step 4.10 | `find . -path ./.venv -prune -o -path ./.git -prune -o -type f -newer runs/step4.10-preparation.20uuxoj6/control.log \( -iname '*.sv' -o … \)` | None |
| Probe run folder | `ls -d runs/step4.13*` | None; the probe has not run |
| Workload identity | SHA-256 of `x_validation_bits.npy` in all 11 relevant run folders | All `5f48bc1d38f0a8d3…`; shape (270, 192), bool |
| Model identities | `protocol.json` `args.seed`/`act_weight` for the ten pair members | Seed 0: `step4.3-pair…/control` (0.0) and `step4.4-sweep…/lambda_0p3` (0.3); seeds 1–4: `step4.5-seeds…/seed_N_{control,penalty}` (0.0/0.3) |
| Accuracy verdicts | `docs/results/step-4.5-repeated-seeds.json` rows | Drops 0.741 / 1.111 / 2.222 / 0.000 / 2.593 pp for seeds 0–4; seeds 1, 2, 4 fail the 1 pp policy, matching `accuracy_status` |

**Freeze claim: confirmed.** No exported RTL, vectors, VCD, synthesis log,
netlist, SDF or bitstream exists for any step 4.3–4.5 or 4.10 model. The
evidence is currently mtime- and search-based only, because the policy is not
yet committed (see N7).

## Findings

### BLOCKING (amend the policy before step 4.13 runs)

**B1. The workload and measurement window cannot be applied as written to
the final netlist, and the probe code already departs from them.**
`fixed_setup.workload` says "one image per clock after reset, identical
schedule for every model". The final 4.14 netlist is the routed **UART board**
(step 3.9 style), where an image enters only after a full UART request
(about 40,529 clocks; step 2.10). `metrics.M1_raw` uses the step 3.5
"stage-aligned useful-work window (first settled state, last settled state]",
which is defined per RTL observation point. A mapped or routed net has no
pipeline stage label, and in a timed run, glitches occur after the settled
sample point. The untracked `scripts/probe_mapped_switching.py` uses a
step 3.8 burst window `(first input − half period − 1 ps, last output check]`
and reads `policy['probe_window']`, a key that does not exist in v1. That would
raise a `KeyError`. As frozen, the window is open to choice after the fact.
Proposed replacement:

> "workload": "All 270 saved validation images (x_validation_bits.npy) in
> saved order, identical bytes and schedule for every model. Standalone
> head-only core runs (probe and zero-delay mapped metrics): one image per
> clock after reset, as step 3.8. Routed UART-board runs: one clean request
> per image at the hardware 104-clock divider with the step 3.9 testbench
> request spacing. Test data are not loaded for inference, export or
> simulation."
>
> "window": "Standalone core: (first input drive − half period − 1 ps, last
> output check], as step 3.8. Routed UART board: (rising clock edge before
> the first request start bit, last reply stop bit + one clock period]. The
> bounds are fixed in clock cycles by the schedule, so they are identical for
> both models of a pair. They include all post-edge settling and glitches."

The probe script should read this key rather than `probe_window`, or the key
name must match.

**B2. The outcome after an implementation failure is undefined.**
`always_report` says a model that fails to fit or meet timing is "recorded,
never dropped". `functional_gate` says a mismatch "blocks the rule result for
that pair until debugged". Neither gives a final outcome. If any primary model
has no routed metric, "mean primary R" cannot be computed, so STOP, PROCEED
and the fallback INCONCLUSIVE all become ambiguous. Proposed addition:

> "implementation_failure": "If any primary model fails the functional gate,
> fit/packing, routing or the 12 MHz timing check on any placement seed, its
> available metrics are reported and the final outcome is INCONCLUSIVE
> (implementation failure), never STOP or PROCEED. A correctness fix to
> project code is rerun on every model of every affected pair. Constraints are
> never relaxed. In the probe, a functional mismatch yields no PAUSE/CONTINUE
> until fixed, and the fixed code is rerun on both models."

**B3. The functional gate contradicts the timed subset.** The gate requires
all 270 images "in each simulated mapped/routed netlist". `timed_image_set`
allows N < 270 timed images. Proposed replacement:

> "functional_gate": "Every model must match its own NumPy integer scores and
> lowest-index argmax for all 270 images in RTL, in zero-delay simulation of
> its mapped netlist and in zero-delay simulation of each routed netlist. Each
> timed simulation must also match on every image it simulates. No activity
> value counts before these checks pass."

### NON-BLOCKING (should clarify)

**N1. The energy scope and the second assumption of the bound are not
stated.** The bound has two steps. First, (total saving)/(total energy) ≤
(core saving)/(core energy), which needs non-core power to be unchanged. This
step is stated. Second, the core's energy reduction must not exceed its proxy
reduction R. That needs per-transition energy not to be systematically lower
in the penalized model; M2 is only a partial check. Only the walkthrough
implies the second step ("even if all core energy scaled with switching"). The
rationale's phrase "the core's own relative reduction" should say "core energy
reduction, assumed not to exceed the larger of the M1/M2 reductions". In the
walkthrough, "falls by less than 1.5%" should read "no more than 1.5%".

The rule also does not say what denominator the 2% refers to. In the step 3.9
UART board, core nets carried 32,580 of 3.49 M timed transitions (about 0.9%).
A board-level saving under the UART workload would therefore be far below 2%
whatever the core result. The rule in effect asks about core energy (a
streaming-accelerator view). State this so a later PROCEED is not read as a
board-level claim.

**N2. Core-net classification for the routed board is not frozen.** In
step 3.9, reassigning four `board.adapter.core.out_valid_*` nets moved the
glitch ratio from 1.68 to 1.81, and 41 nets were left unclassified. Before
computing any routed λ=0.3 result, freeze one of two rules: a hierarchy-prefix
rule with its code hash, or "ambiguous nets reported both ways; the decision
uses the core-inclusive set". Also state that valid-chain flip-flops in the
standalone core count as core (identical in both models).

**N3. The timed-subset rule leaves discretion.** Neither "practical" nor
"fixed from the runtime" is defined. Leakage is low, because only the control's
runtime is used, but seed-1 probe results will already be known. Either fix N
now, or record a formula:
`N = min(270, max(32, floor(B / t_image)))`, with the per-run budget B stated
in advance and t_image measured on the seed-1 control.

**N4. The noise criterion is conservative, and the mean can hide
inconsistency.** The expected range of 3 samples is about 1.7σ, so 2 × range
is about 3.4σ. The SD of the difference between the two 3-placement means,
averaged over 4 seeds, is about 0.41σ. The test therefore leans toward
INCONCLUSIVE, not PROCEED, which is acceptable for a gate that does not lead
to a claim. It ignores variation between model seeds, so one large seed can
lift the mean (for example, R = 0, 0, 0, 10% gives a mean of 2.5%). Report, as
description only, how many primary seeds have R ≥ 2%. Record each placement's
`.asc` hash so that a noise of zero can be shown to come from genuinely
different placements. State that noise is computed per metric.

**N5. Model directories are implicit.** "Step 4.5 matched pairs … seeds 0–4"
does not name the seed-0 λ=0.3 model. It is `runs/step4.4-sweep.zlmbqzyd/lambda_0p3`,
not the λ=0.1 `runs/step4.3-pair.ixlscii4/penalty`. List all ten directories
and their `model.json` hashes (seed 0: control `57700d8b…`, penalty `696dd438…`;
seed 1: `f4cf5d74…`/`bff429b7…`; seed 2: `9a8b17d2…`/`741faaa4…`;
seed 3: `8fe51f7a…`/`54800d39…`; seed 4: `e6bdbcd8…`/`9171fd0b…`).

**N6. The probe's tools depend on step 3.11.** Checklist 3.11 is "built only
if the 4.13 probe says CONTINUE". The probe itself needs a validation-vector
export, mapped capture of new models and fanout counting. The new probe script
provides these. Say that this tooling belongs to 4.13, and that 4.14's
zero-delay M1/M2 reuse the same code unchanged. Checklist 4.13 lists "fit",
but synthesis alone does not establish fit (step 3.8). Either pack, or drop
"fit" from the probe.

**N7. The freeze evidence is not yet durable.** The walkthrough says the hash
is "recorded in the commit that adds it", but nothing is committed, and the
walkthrough omits the hash itself. Commit before running 4.13, and write the
SHA-256 into the walkthrough. **Measurement has not started, so amending now
is legitimate.** Issue the change as v1.1 (or v2) with an `amendments` entry
(date, reason: this review, old hash `9b1c2faa…`), keep v1 in git and record
the new hash.

**N8. PAUSE has no follow-up rule.** State that resuming 3.11/4.14 after a
PAUSE requires a new, dated policy, so the threshold cannot be reinterpreted
afterwards.

### NOTES

- **Input register.** The policy includes the input register in the core; it
  does not exclude it. The `x` port nets are excluded, which is consistent with
  step 3.8's categories. Both models see identical inputs, and probably use
  nearly all 192 bits, so these toggles are common to both. They dilute R
  toward STOP. That is conservative, applies equally to both models, and is
  closer to the total-energy bound. Including the register is acceptable.
- **Decision logic otherwise complete.** Negative R falls below 2%, so PAUSE
  or STOP can apply, which is correct. If one metric is at or above 2% and the
  other below, STOP does not apply; the result is PROCEED if that same metric
  passes the noise test, and INCONCLUSIVE otherwise. PAUSE and CONTINUE are
  complements. A control value of zero is impossible in practice; the script
  raises an error, which B2's wording should label INCONCLUSIVE. OR-ing M1 and
  M2 gives two chances to avoid STOP, a mild multiplicity effect that is
  acceptable because PROCEED is not a claim. Compare values without rounding.
- **Probe bias.** Seed 1 has the smallest logical reduction of the primary
  seeds (16.04%), so it is a mildly conservative choice, fixed in advance by
  rule. A zero-delay mapped run omits glitches (about 1.68 extra transitions
  per settled change in step 3.9). Synthesis also removes constant gates, and
  the penalty may create more of them. The direction of both effects on R is
  unknown. A 2% threshold against a logical R of about 16% leaves a wide
  margin, so a false PAUSE would need the mapped R to be diluted about 8-fold.
  M2 fanout in the mapped netlist is not comparable with M2 in the routed
  netlist.
- **Timed-model limits remain.** Icarus filters narrow pulses inertially, uses
  one delay corner and has no timing checks (step 3.9). These bound what "glitch"
  means here.
- **Seed-0 handling** is consistent with 4.5: secondary and reported
  separately.
- **Consistency.** "About 17%" and "about 1.5 pp" match 16.71% and 1.48 pp.
  Seeds, placement seeds 1–3 and outcome names agree across the JSON,
  walkthrough and checklist; the checklist lists outcomes in a different order,
  which is cosmetic. Item 3 of the discussion is an earlier proposal without
  INCONCLUSIVE or the probe. It is a dated record that the frozen rule
  supersedes; a pointer would help. Nothing claims energy, novelty or venue
  suitability, and the `limits` fields are appropriate.
- **Accuracy unchanged.** `accuracy_status` keeps seeds 1, 2 and 4 failed under
  `validation_selection_policy_v1` (1 pp), and requires a separately named
  policy for any other allowance. A PROCEED does not make λ=0.3 a selected
  model.

## Verdict

**Freeze confirmed; three blocking findings before measurement.** No hardware
artifact of any new model exists. The decision structure is sound: the
thresholds, the two-stage probe and final rule, the seed-0 exclusion and the
unchanged accuracy verdicts. It is suitably conservative and does not
overclaim. However, the final-stage workload, measurement window and
functional gate cannot be applied as written to the routed UART board, and the
outcome after a fit, timing or functional failure is undefined (B1–B3). The
in-progress probe script already relies on a window key that the frozen v1
does not contain. Recommend a recorded amendment (v1.1/v2 with an amendment
entry and new hash) that adopts the wording above and addresses N1, N2, N5 and
N7. Commit it before step 4.13 runs. I will recheck the amended policy on
request.

## Recheck of v2

Date: November 18, 2026. Same constraints as before: I read files, made
hash/JSON checks and ran the unit tests. I did not export, synthesize, route
or simulate any model.

### Checks performed

| Check | Result |
|---|---|
| `git show cde1fbd:docs/experiments/hardware-switching-stop-rule-v1.json \| shasum -a 256` | `9b1c2faa…3458bc`. v1 is committed unchanged, and the working copy is identical |
| `shasum -a 256 docs/experiments/hardware-switching-stop-rule-v2.json` | `91a555c5…963720`, matching the walkthrough. Not yet committed |
| `shasum -a 256` of the ten listed `model.json` files | All ten full hashes match `models.seed_0…seed_4`. Seed-0 λ=0.3 points correctly to `step4.4-sweep…/lambda_0p3` |
| v1/v2 field comparison (Python) | Threshold, `reduction`, primary seeds, placement seeds and the PAUSE/CONTINUE logic are unchanged. The probe text differs only in wording. The M1/M2 text was clarified, and the window moved to `fixed_setup.window` |
| `ls -d runs/step4.13*` | None; the probe has still not run |
| `.venv/bin/python -m pytest tests/test_probe_mapped_switching.py -q` | **11 passed in 0.07 s** |
| Read through `scripts/probe_mapped_switching.py` | See the findings below |

**Original findings.**
- **B1 resolved.** The workload is now split between the standalone core and
  the UART board, and each has a window defined by its fixed schedule. The
  script reads `fixed_setup.window.standalone_core`. It computes
  `(first_input_ps − 41667 − 1, last_output_check_ps]`, which matches v2;
  `HALF_PERIOD_PS = 41667`.
- **B2 resolved.** `implementation_failure` comes first in `decision_order`.
  A non-positive control raises an error, so the probe gives no decision.
- **B3 resolved.** The functional gate is split: 270/270 for RTL, mapped and
  zero-delay routed simulations, and every simulated image in timed runs.
- **N1, N3–N8 addressed.**

**Probe script against the v2 probe definition.**
- **Core set:** ledger categories `lut`/`carry`/`ff`. `ff` is a catch-all, but
  `mapped_activity.instrument_json` only lets through known primitive pin
  shapes and outputs; anything else raises an error.
- **Fanout:** counts the deduplicated `cell:type.port` user strings, which are
  single-bit primitive pins, excluding the net's own driver and `port:`
  references. A `primary:` reference raises an error.
- **Decision:** PAUSE if and only if both R < 2%, with no rounding.
- **Exact-match checks:** the full-pass lines `PASS: 270/270 vectors` (RTL)
  and `PASS: 270/270 mapped vectors` are required. X/Z values must be zero
  inside the window. The event ledger and port bus are validated.
- **No test data:** inputs are `x_validation_bits.npy` only. A run folder
  containing `x_test_bits.npy` is rejected, and `test_evaluated` must be
  `False`.
- **Provenance:** checked against the training manifest and status, plus
  seed, split, λ and `act_mode`. Run paths and model hashes must equal
  `policy.models.seed_1`, and the two validation workloads must be identical.
  `plan.json` is written before capture. Source and policy hashes are checked
  again at the end.

### Findings

**BLOCKING**

- **R1. The routed core-inclusive rule would count known interface activity
  as core.** v2 `core_definition.routed_uart_board` treats every
  `category() == 'unclassified'` net as core for the decision. In step 3.9,
  that group was the reset chain, TX pin, VCC and interface carry cells,
  with about 529k settled changes. The core had 12,178 settled and 32,580
  timed transitions. That activity is identical in both models, so counting
  it would dilute R about 17-fold and push mechanically toward STOP. The
  problem traces partly to my own N2 wording ("ambiguous nets … core-inclusive").
  The truly ambiguous `board.adapter.core.out_valid_*` nets are already
  `core` under `category()`. Fixing this now is a definition repair, not a
  change informed by results, because no new-model hardware result exists.
  Proposed replacement for the last two sentences:

  > "The decision uses exactly the nets with category() == 'core'. Nets
  > classified 'unclassified', 'interface', 'clock', 'global_buffer' or 'io'
  > are excluded from the decision and reported separately by name and count.
  > As a sensitivity check only, M1/M2 are also reported with the
  > board.adapter.core.out_valid_* nets moved to interface. The classification
  > code hash is recorded with each result."

  This finding concerns step 4.14 only. It does not affect the 4.13 probe,
  which uses the standalone core, so the probe could run on v2 as is. Even
  so, amending to v3 before 4.13 keeps one policy for both stages.

**NON-BLOCKING**

- The script's docstring usage line still shows `--policy …-v1.json`. The code
  rejects v1, so the usage line is stale.
- The 11 tests cover the fanout, core-metric, unknown-value, width,
  primary-reference, decision and reduction helpers. They do not cover the
  window bounds, `check_run`, the policy model binding or the v1 rejection.
- The script checks the policy schema but does not pin its hash. The hash is
  recorded in `plan.json`, so this is acceptable if the result is audited
  against `91a555c5…`.
- Checklist row 3.11 still says it "adds core-net classification and
  fanout-weighted counts (M2)". v2 assigns that standalone tooling to 4.13.
  3.11 should say routed-board classification and reuse of the 4.13 M2 code.
- The walkthrough's numbered decision list omits the implementation-failure
  outcome that comes first (it appears later in the text). Its sentence
  "270/270 … before any activity number counts" predates the split gate.
  The figure "0.15% of board transitions" is a transition share, not energy.

**NOTE**

- The amendment record is complete: superseded hash, commit and reason.
  Nothing in v2 alters the threshold, metrics, seeds or decision structure
  in a results-informed way, since no new-model measurement exists.
- `accuracy_status` still leaves the step 4.5 verdicts unchanged.

### Recheck verdict

**B1–B3 are resolved, and the probe script implements the v2 probe
definition.** One new blocking item, R1, affects only the routed stage
(4.14). Fix it with a recorded v3 amendment, preferably before 4.13 runs, and
commit v2/v3 before any probe run.

## Recheck of v3

Date: November 18, 2026. I read files, made hash/JSON checks and ran the unit
tests only; no model was exported, synthesized or simulated.

- **Hashes.** `git show f5f8304:…-v2.json | shasum -a 256` gives
  `91a555c5…963720`, so v2 is committed unchanged. v3 is
  `5d22135a…7236930d`, matching `POLICY_SHA256` in the probe script. v3 and
  the script are not yet committed.
- **v2 to v3 field diff (recursive Python comparison).** Only four fields
  differ: `schema`, `approved_by`, a second `amendments` entry (supersedes v2
  `91a555c5…`, commit `f5f8304`, reason R1), and
  `core_definition.routed_uart_board`, which now holds my R1 wording verbatim.
  Threshold, metrics, seeds, windows, the functional gate and the decision
  order are unchanged.
- **R1 resolved.** The routed-stage decision now uses exactly the nets with
  `category() == 'core'`.
- **Script.** The policy is loaded through `load_policy`, which requires
  schema v3 and the pinned hash. `check_frozen_models` binds the run folders
  and model hashes. `window_bounds` gives `(first_input_ps − 41667 − 1,
  last_output_check_ps]`. The docstring now points to v3.
- **Tests.** `.venv/bin/python -m pytest tests/test_probe_mapped_switching.py -q`
  gives **14 passed in 0.51 s**.
- **Not run.** `runs/step4.13*` does not exist yet.

**Verdict: GO for the step 4.13 probe**, once the v3 policy, probe script and
tests are committed. No blocking findings remain.
