# Step 4.13 independent review: mapped-switching screening probe

Reviewer: independent verification agent, Nov 18, 2026.
Verdict: **no blocking finding. The CONTINUE decision is reproduced and
independently confirmed.** Two non-blocking findings about interpretation
should be stated in the walkthrough.

## Scope

- Policy `docs/experiments/hardware-switching-stop-rule-v3.json`
  (sha256 `5d22135a…6930d`, committed in `42831fe`).
- Probe code `scripts/probe_mapped_switching.py` and
  `tests/test_probe_mapped_switching.py` (commit `3c2e1e6`).
- Evidence `runs/step4.13-probe.nakln11l/` (`plan.json`, `result.json`,
  `control/` and `penalty/`).
- Pair: seed-1 control and seed-1 lambda-0.3 diagnostic from
  `runs/step4.5-seeds.vyq2h2nf/`.
- Only validation data were used. No test file was read by the probe or by
  this review. No tracked file was modified. Scratch work is in
  `runs/step4.13-review.independent/`.

## Commands

```bash
mkdir -p runs/step4.13-review.independent
.venv/bin/python scripts/probe_mapped_switching.py \
  runs/step4.5-seeds.vyq2h2nf/seed_1_control runs/step4.5-seeds.vyq2h2nf/seed_1_penalty \
  --policy docs/experiments/hardware-switching-stop-rule-v3.json \
  --out-parent runs/step4.13-review.independent        # -> step4.13-probe.ygnq800p/
# Independent oracle: our own netlist writer, testbench, VCD parser and fanout counter
.venv/bin/python runs/step4.13-review.independent/oracle/oracle.py \
  runs/step4.13-review.independent/step4.13-probe.ygnq800p/<model> \
  runs/step4.5-seeds.vyq2h2nf/seed_1_<model> runs/step4.13-review.independent/oracle/<model>
# Analysis only: attribute M1 to regions by matching each net against single-gate outputs
.venv/bin/python runs/step4.13-review.independent/oracle/decompose.py ...
.venv/bin/python -m pytest tests/test_probe_mapped_switching.py -q    # 14 passed
```

## 1. Provenance

| Check | Result |
|---|---|
| Policy file hash = frozen hash, and equals the copy in `42831fe` | pass |
| Hashes of all nine source files in `plan.json` = `git show 3c2e1e6:<file>` and = working tree | pass (9/9) |
| `model.json` hashes = `policy.models.seed_1` (control, penalty) | pass |
| `plan.json` written before capture | pass: plan 23:16:45.4808 s; first export file 23:16:45.4877 s; code commit 23:16:38 |
| Test data | Probe reads only `x_validation_bits.npy`/validation files; it rejects runs containing `x_test_bits.npy` or `test_evaluated != false`. The `capture_baseline_waveform` import uses only `write_parameters`/`validate_events`; its test-data path (`capture()`) is never called. `dlgn.data`/`experiment` are not imported. |
| Vectors | Our own decoding of `x.hex`, `exp_scores.hex` and `exp_class.hex` matches `x_validation_bits.npy`, `validation_scores.npy` and `validation_classes.npy` for all 270 images in both models (lowest-index argmax). |

## 2. Reproduction

A fresh rerun (`step4.13-probe.ygnq800p`, about 25 s) passed. It gave the same
`metrics`, window and event ledger for both models, and the same reductions to the
last bit (M1 0.03206383675080915, M2 0.039278152640639497) and the same decision,
CONTINUE. Every regenerated artifact has the same SHA-256 hash as the original: `dlgn_top.sv`, hex
vectors, `mapped.json`, `net-ledger.json`, `mapped_core.v`, `events.csv`
and VCD size. Synthesis is deterministic here.

## 3. Independent oracle

We did not use the project's instrumentation, `write_verilog`, ledger or VCD parser.
Starting from `mapped.json`, we wrote our own Verilog netlist (one wire `n<bit>` per
numeric bit, with LUT_INIT copied from the JSON) and simulated it against the yosys
`cells_sim.v` primitives using our own testbench. The testbench has the same 12 MHz
schedule: three reset negedges, then one image per negedge. It dumps every
DUT wire. We then parsed the VCD with our own parser, keeping the last value per
identifier per timestamp, over the window (first capture − 41,667 − 1, last output check].
Fanout = number of cell input-pin bits on the net. It excludes the driver, top-level
ports and constants. Core nets are classified by driver: SB_LUT4.O, SB_CARRY.CO or
SB_DFF*.Q.

| Quantity | Control (probe) | Control (oracle) | Penalty (probe) | Penalty (oracle) |
|---|---:|---:|---:|---:|
| Window (ps) | (250001, 22875184] | same | (250001, 22875184] | same |
| Mapped pass | 270/270 | 270/270, 0 mismatches | 270/270 | 270/270, 0 mismatches |
| Core nets (LUT/carry/FF) | 3,370 (2,908/123/339) | same | 3,291 (2,829/123/339) | same |
| M1 | 384,982 | **384,982** | 372,638 | **372,638** |
| M2 | 1,061,277 | **1,061,277** | 1,019,592 | **1,019,592** |
| Unknown changes in window | 0 | 0 | 0 | 0 |
| Max records per ID per timestamp | 1 | 1 | 1 | 1 |

The per-category values (lut/carry/ff, M1 and M2) also match exactly. Per-net fanout
agrees with the probe ledger for all 3,370 and 3,291 nets. **No discrepancy.**
R1 = 3.2064 % and R2 = 3.9278 %, both ≥ 2 %, so the frozen rule gives CONTINUE.
The values were compared unrounded. Either metric alone would be enough.

## 4. Methodology

- **Fairness.** Both models use the same window bounds, the same event ledger
  (identical input/output timestamps), the same 270-image schedule and the same
  yosys/iverilog command lines and tool binaries. Both have LAT 3 and the same
  architecture. The pair is matched.
- **Common activity (dilution).** The frozen core definition includes the input
  register, popcount adders, score/class/valid registers and argmax. These are
  largely common to both models. The input register is exactly common
  (13,097 toggles in both). Including them lowers R compared with a layer-only
  view. This follows the policy, which defines the decision quantity as core
  switching. It is not a defect.
- **Constant/merged gates.** The penalty netlist has 79 fewer LUT4s
  (2,829 vs 2,908). Removed constant gates add no toggles in either model.
  Unequal logic merging is part of the real hardware outcome. Resource counts are
  recorded in `result.json`.
- **Zero-delay.** Counts are settled per-timestamp changes. They include no glitches and are not routed.
  This is acknowledged in `limits`.

## 5. Where 16 % becomes 3.2 % (ANALYSIS, not a validated measurement)

`decompose.py` evaluates the pre-score combinational cone in Python for each image,
working from the input-register FFs. A net counts as "a gate output" if its 270-image vector
equals some hard layer-gate output or its complement. The labels are heuristic:
equal vectors can collide, and each net takes the first matching layer.

| Region (M1) | Control | Penalty | Δ |
|---|---:|---:|---:|
| Input-register FFs (192) | 13,097 | 13,097 | 0 |
| Pre-score nets equal to a single layer gate (872 / 811 nets) | 91,543 | 80,210 | −11,333 (−12.4 %) |
| Pre-score LUTs equal to no single gate: popcount adders and merged gate chains (1,873 / 1,858) | 230,123 | 229,450 | −673 (−0.3 %) |
| Pre-score carries | 6,417 | 6,506 | +89 |
| Post-score argmax (LUT + carry) | 26,593 | 26,168 | −425 |
| Score/class/valid FFs | 17,209 | 17,207 | −2 |
| **Total** | **384,982** | **372,638** | **−12,344 (−3.2 %)** |

Logical settled changes per layer: L1–L4 control 76,674 / 89,266 / 101,131 / 112,531,
penalty 55,543 / 67,103 / 87,636 / 108,448. The reductions are 27.6 / 24.8 / 13.3 /
**3.6 %**. Three effects explain most of the shrinkage:

1. The penalty saves mostly in layers 1–2. Layer 4 drives the popcount and changes only 3.6 %.
2. Activity in the popcount and adders, driven by layer 4, is about 60 % of mapped M1,
   and it is essentially unchanged.
3. Mapping packs most gates into multi-gate LUTs. Only about 870 of 4,000 gates survive as
   their own nets, so the logical saving of 60,872 changes appears as about
   11,300 fewer toggles on gate-equivalent nets.

## Findings

- **NON-BLOCKING N1 (M2 interpretation).** About half of the M2 reduction
  (20,879 of 41,685) comes from the input-register FFs. Their toggles are
  identical in both models (13,097), but their load differs: 2,383 vs 2,192
  input pins. This is a connectivity (load) difference, not a switching
  difference. It is consistent with the M2 definition, but the walkthrough
  should say so. Without the input register, R2 = 2.37 %. The decision does not
  change, because R1 alone exceeds 2 %.
- **NON-BLOCKING N2 (reporting).** The walkthrough should present R1/R2 as
  core-inclusive by the frozen definition. It should also note that the gap from
  logical 16.0 % to mapped 3.2 % comes mostly from unchanged popcount/adder activity
  and the small layer-4 reduction (section 5, labelled as analysis).
  CONTINUE means only "build 3.11/4.14". It is not evidence of an energy saving.
- **NOTE N3.** The margin is modest: R1 is 1.21 pp above the threshold, from one seed with
  zero delay. The probe correctly declines to make a final decision.
- **NOTE N4.** In `plan.json`, `tool_versions` records `["--version"]` for
  yosys-config and `[]` for vvp, so it does not capture their versions. The
  resolved binary paths are recorded, and the Homebrew Cellar paths include
  versions. This is a cosmetic provenance gap.
- **NOTE N5.** Commits `42831fe` and `3c2e1e6` have the same committer second
  (23:16:38). The probe started 7 s later. The policy precedes the probe. No other
  hardware export of these models exists under `runs/`, but the reviewer cannot
  prove that no earlier, unrecorded export ever took place.
- **NOTE N6.** Deleting `mapped.vcd` by design is acceptable. The rerun showed
  that every input to the VCD is hash-identical and regenerates deterministically.

## Verdict

Provenance, reproduction and the independent oracle all pass with exact
agreement. CONTINUE is correctly applied under the frozen v3 rule. There is no
blocking finding. Address N1 and N2 in the step 4.13 walkthrough.
