# Step 3.5 independent verification

Reviewed November 16, 2026 by the independent `verify_step_3_5` agent using
the engineering code-review skill.

## Verdict

**No blocking finding remains after correcting and rechecking the input-data
continuity guard.** Step 3.5 may be complete for the fixed standalone streaming
capture. Each observation has 450 known settled states and the same 449
adjacent-image intervals, with pipeline offsets handled explicitly.

These are staggered per-observation windows, not one device-wide physical
measurement interval. This review approves neither an aggregate physical-net
switching total, logical-layer/NumPy transition agreement, power nor energy.

## Methodology and implementation review

I reviewed [report_activity_windows.py](../../scripts/report_activity_windows.py),
the existing [capture bench](../../rtl/tb_activity_capture.sv),
[exporter](../../dlgn/export_verilog.py),
[walkthrough](../steps/3.5-define-activity-windows.md) and
[tracked summary](../results/step-3.5-activity-windows.json).

- The first settled frame is a baseline. The interval is
  `(first settled sample, last settled sample]`, with 450 states and 449
  neighboring pairs. It excludes startup-to-frame-0 changes without dropping
  valid end frames.
- Raw input `x` is driven half a cycle before capture into `l0`. For a fully
  layer-pipelined design, combinational `lD_c` is available one cycle before
  registered `lD`. Score-bank/winner and final output offsets follow the
  presence of head registers and the exported stage count.
- Sampling at availability plus 1 ps avoids nonblocking-update races. The
  sampler carries state at quiet timestamps; a requested sample need not have
  its own explicit timestamp record in the VCD.
- The validator requires all expected widths and a 1 ps timescale. It checks
  the full clock, reset, input-valid and output-valid change schedules, every
  input transaction marker, known observation endpoints and archived I/O
  references. After correction, it also checks every raw input-data change.
- Legitimate identical neighboring images remain separate transactions and
  intervals even when their signal values do not change.
- Archive hashes bind all capture inputs, and all hashes are checked again
  after validation. Reports use fresh directories and preserve exact manifest
  and analyzer source copies. Existing captures are not overwritten or called
  new simulations.

The actual nominal clock remains 12 MHz with the existing 83,334 ps simulated
period from 1 ps rounding. Archived implementation constraints are unchanged;
no synthesis or placement/routing was performed here. Generic toy tests of
other register configurations do not establish their physical FPGA fit.

## Independent tests

I authored [test_activity_windows.py](../../tests/test_activity_windows.py).
My corrected targeted run passed **22 tests in 0.78 seconds, with no skips**:

```bash
.venv/bin/python -m pytest tests/test_activity_windows.py -q
```

- Four independent schedule cases derive all offsets for every combination
  of layer and head registers, using 450 states and 449 pairs.
- Four self-contained Icarus cases run the shipped capture bench and independently
  decode the resulting VCD. They check each stage's known endpoint samples,
  duration, input boundaries and delayed output boundaries for sixteen input
  patterns. This is a finite functional test, not a formal or physical proof.
- One repeated-all-zero-input case verifies that sixteen states still imply
  fifteen adjacent pairs despite the absence of data changes.
- Thirteen fault cases exercise a one-tick ledger error, input-valid bubble,
  reset during frames, an unknown layer sample, an incorrect input index,
  changed expected scores, an unrebound trace hash, missing final output,
  off-phase input data pulse, drain data pulse, between-sample reset pulse,
  between-sample valid pulse and timescale mismatch. Semantic faults rebind the
  trace hash so validation must inspect behavior rather than reject only a hash.
  Rejected reports retain failed status.

The root's final full-suite run passed **152 tests in 11.78 seconds, no skips**.
This is the root's reported full run, separate from my targeted run. These
22 cases are included in 152, not additional unique cases beyond it.

## Blocking finding, fix and correction verification

**Expected:** the declared fixed workload changes input data only at falling
edges and holds the final input during drain. A capture containing extra data
pulses must be rejected even if values return before endpoint samples.

**Actual before correction:** the first validator checked `x` only at sampled
states and at the final drain state. Both a 1 ps off-phase pulse and a 1 ps
drain pulse returned successful reports. The two independent fault tests
failed with `DID NOT RAISE ValueError`; the expanded run had 20 passing and
two failing cases.

**Reproduce:** run the targeted command above against the earlier validator,
specifically the `x_between_samples` and `x_during_drain` cases. Original
failing fixture captures, accepted reports, copied analyzer sources, test file
and an observation summary are preserved in
`runs/step-3.5-verifier-debug/`. The root also preserved a separate reproduction
in `runs/step-3.5-debug/off-phase-reproduction.yjmelv2x/`.

**Root cause:** endpoint equality does not establish temporal continuity.
An extra change between samples can contaminate subsequent raw-event counting
while every checked endpoint remains correct.

**Fix:** collect every normalized `x` change and compare it with the exact
initial-zero/falling-edge image-change schedule, suppressing only legitimate
repeated values. Reject any off-phase or drain change.

**Independent recheck:** all 22 tests pass with this guard. I also directly
re-ran both preserved originally accepted captures through the corrected
validator. Both now fail with
`Input data changes outside the falling-edge/held-input schedule`. The result
is saved in `runs/step-3.5-verifier-debug/corrected-verification.json` without
deleting the earlier passed evidence. No clock, endpoint or test requirement
was weakened. Keep both semantic pulse regressions as prevention.

The separate initial report-layout mismatch was an API/schema correction:
top-level versus nested `windows` fields. The final wrapper matches the
initial API and unchanged independent test assertions. It did not change the
measurement policy or timestamps.

## Independent full-capture audit

I independently ran `report_windows` on both previously verified captures:

- `baseline-waveform.xs90rtvt/activity-windows.p4p5y9h0/result.json`
- `baseline-waveform.q2umneq1/activity-windows.kuy7li2p/result.json`

Both paths are under `runs/digits_w1000/`. I then used a separate test-side VCD
decoder and independently derived integer-time expectations to audit those
reports and the root's final corrected primary
`baseline-waveform.xs90rtvt/activity-windows.lf7s8aqq/result.json`.

For each of the **14 observations**, all 450 endpoint values are known and
reset is low. Input/registered-input values match the ordered input words;
score-bank/output scores and winner/output classes match archived references
at their distinct availability times. Every output marker/index/count agrees.
I did not compare logical-layer values or transitions with NumPy; that remains 3.7.

The independent audit also checks every recorded clock edge and all reset,
valid and raw-input changes, including held input through drain. Each report's
**16 capture-artifact hashes**, **four current source hashes**, **five saved
analysis-artifact hashes** and capture-manifest hash passed.

All three reports agree on these windows:

| Observation | Start excluded, ps | End included, ps |
|---|---:|---:|
| Raw input `x` | 250,003 | 37,666,969 |
| `l0`, all `lD_c` and `lD` in this head-only candidate | 291,670 | 37,708,636 |
| `sc_flat` and `best` | 375,004 | 37,791,970 |
| Registered `scores` and `class_out` | 458,338 | 37,875,304 |

Every window contains 450 states/449 pairs and spans 37,416,966 ps. The
diagnostic burst envelope instead spans first drive at 250,002 ps through the
final output check at 37,875,304 ps. They are different definitions for
different questions; neither is automatically an energy-per-prediction denominator.

The reproducible independent audit and summary are archived in
`activity-windows.p4p5y9h0/independent-verification.py` and
`independent-verification.json`. Re-run from the repository root:

```bash
.venv/bin/python runs/digits_w1000/baseline-waveform.xs90rtvt/activity-windows.p4p5y9h0/independent-verification.py
```

The audit records/checks the independent decoder's test-file hash. Raw runs
remain local and gitignored; a fresh clone needs those artifacts or reproduced
captures, while the synthetic regressions are self-contained.

## Research boundaries

These windows make adjacent-image comparisons comparable at each observation
without discarding frame pairs because of pipeline latency. They do not
establish a universal common physical-time crop, and sums of staggered
observation counts must not be called device-wide switching or physical energy.

Known endpoint states do not prove the absence of intermediate events or X/Z
states inside a window. The event counter must retain that distinction from
settled-state sampling. Signal categories and logical duplicate selection remain
3.6, settled logical/Python comparison remains 3.7, and mapped activity/glitches
require separate evidence. No activity totals or rates are reported by this step.

No power estimate, electrical measurement, lower energy, regularizer benefit
or novelty is demonstrated. Continue with matched target, clock, architecture,
input order and workload, validation-based model selection and repeated seeds.
The already inspected historical digits data remain exploratory.
