# Step 3.2 independent verification

Reviewed November 16, 2026 by the independent `verify_step_3_2` agent, using
the engineering code-review skill.

## Verdict

No blocking finding remains for **waveform-recording support on Icarus**.
Recording preserves the checked score/class behavior, creates observable VCD
data when enabled, and creates no VCD when disabled in fresh exports.
Step 3.2 can be marked complete within that scope. Full baseline capture,
transition accounting, measurement windows and power evidence remain later steps.

## Independent inspection

I reviewed [check_waveform_recording.py](../../scripts/check_waveform_recording.py),
the existing [simulation script](../../sim/run_sim.sh), the
[exporter/testbench generator](../../dlgn/export_verilog.py), the
[walkthrough](../steps/3.2-verify-waveform-recording.md), tracked
[result](../results/step-3.2-waveform-recording.json), and
[checklist additions](../PROJECT_CHECKLIST.md).

- `DUMP` is a compile-time testbench option; the inference RTL and inputs are
  identical within each on/off pair. The off mode explicitly unsets the
  environment variable. A nonempty `DUMP=0` would also enable recording, as
  correctly documented.
- Fresh attempt and per-mode folders prevent stale traces/logs from satisfying
  this check. The result records success/failure separately from older evidence.
- Each simulation must pass every integer score and predicted class against
  freshly generated NumPy reference vectors. Hash comparisons also bind each
  on/off pair's RTL, bench, parameters and vectors.
- The inspector requires the expected-width input, output, control and logical
  layer declarations, advancing timestamps and known observations. Clock,
  reset and valid signals show both values; input data changes. It tolerates
  unknown initialization and identifiers shared by aliases without summing them.
- The inspector is a narrow observability check, not a general VCD compliance
  checker, activity analyzer or proof that every waveform sample is correct.
  The walkthrough explicitly preserves those distinctions.

## Independent regressions

I authored [test_waveform_recording.py](../../tests/test_waveform_recording.py).
The targeted command passed **14 tests in 0.60 seconds, with no skips**:

```bash
.venv/bin/python -m pytest tests/test_waveform_recording.py -q
```

- Four independent direct-simulation cases cover all combinations of layer
  pipelining and head pipelining. Each uses a reproducible three-layer,
  40-gate-per-layer toy network and all sixteen four-bit input values. Both
  recording modes pass 16/16 score/class comparisons, preserve identical
  sources/vectors, and satisfy independent trace declarations/time/control
  checks. These are repeated evaluations of sixteen distinct patterns, not
  128 distinct inputs or an exhaustive proof for the trained network.
- One synthetic trace demonstrates acceptance of alias identifiers and unknown
  startup followed by known data.
- Nine independently constructed trace faults demonstrate rejection of missing
  layer declarations, wrong bus width, absent known layer values, static clock,
  static input, backwards time in two placements, missing timescale and missing
  end-of-definitions marker.

No test failure or unexpected simulation behavior required a debugging fix.
No inference RTL or training code changed for this step.

## Independent trained-model rerun and provenance

I separately executed:

```bash
.venv/bin/python scripts/check_waveform_recording.py runs/digits_w1000 --n 8
```

My fresh result is
`runs/digits_w1000/waveform-check.am2eksx1/result.json`.
The root's separate primary result is
`runs/digits_w1000/waveform-check.njxy5prx/result.json`.

Both runs agree:

| Core | Recording off | Recording on | VCD bytes | Last timestamp |
|---|---|---|---:|---:|
| Original combinational | 8/8 score/class PASS, no VCD | 8/8 score/class PASS | 177,244 | 145,000 ps |
| Head-only pipeline | 8/8 score/class PASS, no VCD | 8/8 score/class PASS | 179,200 | 155,000 ps |

These use **eight distinct historical images**, repeated across modes and
architectures. There are not 32 distinct test images. VCD byte hashes may
differ between fresh runs because the format includes run metadata; equality
of entire VCD files is not required.

For **each** attempt I independently checked all seven recorded source/model/
input hashes, both simulator executable hashes and all 42 saved per-mode file
hashes against disk. I decoded the packed input hex back against the first
eight saved rows in their unchanged order, and independently decoded the
score/class hex against `dlgn.hard.scores` and its lowest-index argmax. The
verification summary is retained in
`waveform-check.am2eksx1/independent-verification.json`.

The root's final full-suite run including all fourteen new recording cases
passed **85 tests in 9.34 seconds, with no skips**. That count is the root's
reported full-suite run, distinct from my independent targeted run. The
fourteen cases are included in 85, not additional unique tests beyond it.

## Research direction and remaining limits

The checklist incorporates the recovered professor-feedback summary as
continuation tasks: complementary activity metrics in 3.10, validation-only
experiment preparation in 4.10 before training sweeps, separate Gray-coding
assessment in 4.11, and manuscript review in 7.6. It preserves the existing
thermometer encoding and historical baseline; no restart or untested encoding
benefit is implied. The feedback is appropriately labeled a prior-conversation
summary rather than a verbatim professor quote.

The recording check uses the bench's existing **nominal 100 MHz functional
clock**, not a timing-qualified 12 MHz power workload. It covers the core,
not UART, physical board operation, full test-set capture or routed delays.
Only Icarus recording is established here; other simulator backends are outside
this evidence.

Step 3.3 must freeze architecture, clock, image order and valid/workload policy
for full baseline capture. Steps 3.4–3.7 still need alias-aware counting,
explicit unknown handling, reset/fill/drain exclusions, category separation and
settled logical-output comparison with Python. Simulator events are not
physical glitch evidence. Neither lower hardware energy nor the novelty or
effectiveness of the training penalty is established by this infrastructure.
The research direction remains conditional on matched, validation-selected,
repeated experiments and separate mapped/power evidence.

Raw runs remain local and gitignored. A fresh clone needs those artifacts or
reproduced trained-model runs; the independent toy regressions are self-contained.
