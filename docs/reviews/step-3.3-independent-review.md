# Step 3.3 independent verification

Reviewed November 16, 2026 by the independent `verify_step_3_3` agent, using
the engineering code-review skill.

## Verdict

**No blocking finding remains for the scoped full baseline waveform capture.**
Step 3.3 may be marked complete. The trace contains all 450 historical inputs
in the saved order and all 450 exact integer-score/class responses, using the
declared head-only core and streaming workload. This does not complete activity
analysis, switching-window approval, Python/RTL switching comparison, mapped
glitch analysis, device power estimation or electrical measurement.

## Code and methodology inspection

I reviewed [capture_baseline_waveform.py](../../scripts/capture_baseline_waveform.py),
[tb_activity_capture.sv](../../rtl/tb_activity_capture.sv), the reused
[observability inspector](../../scripts/check_waveform_recording.py),
[walkthrough](../steps/3.3-capture-the-baseline-waveform.md),
[tracked result](../results/step-3.3-baseline-waveform.json), and the checklist's
continuation from 3.2 to 3.3.

- The primary capture regenerates the head-only inference core from the saved
  model and requires exact source/parameter agreement with `uart_comb_head`.
  It validates the existing saved implementation rather than running a new
  implementation or substituting a different trained model.
- The selected architecture is appropriate for a hardware-associated baseline:
  the older non-head design failed its 12 MHz requirement and the full-layer
  candidate remains over capacity. Neither failure is hidden or reclassified.
- The clock is explicitly nominal 12 MHz, rounded to a fixed 83,334 ps period
  on Icarus's 1 ps time grid: 11,999,904.000768 Hz. This does not change the
  archived FPGA clock constraint. Future matched captures must use the same
  rounding and workload policy.
- The driver changes reset/data/valid at falling edges. It checks every output
  1 ps after a rising edge, after nonblocking register updates have settled.
  The extra observation delay is not another pipeline stage or a physical
  propagation-time measurement.
- The bench records explicit input/output indices and counters, cycle index,
  completion marker and an event ledger. Transactions are counted even when
  adjacent images have identical values. The last input remains stable during
  drain; no extra invalid input changes are introduced.
- Fresh attempt directories and running/passed/failed status preserve evidence
  and prevent an older trace from passing as a new capture. Sources, ordered
  inputs, generated reference words, commands, logs, executable identities and
  trace hashes are recorded. No inference RTL or training code changed.

`validate_events` verifies index order, relative cadence and latency, and that
completion follows the final output. It is not a complete independent proof
of the reset schedule or three-falling-edge drain. I checked those absolute
boundaries separately from the VCD, as detailed below. The reused 3.2 inspector
requires an input-value change and is applied to this varied historical data;
the generic bench itself supports repeated/all-zero inputs.

## Independent tests

I authored [test_baseline_waveform.py](../../tests/test_baseline_waveform.py).
The targeted command passed **10 tests in 0.24 seconds, with no skips**:

```bash
.venv/bin/python -m pytest tests/test_baseline_waveform.py -q
```

- Four cases compile and run the shipped capture bench across all combinations
  of layer and head pipelining. A separate test-side VCD decoder checks all
  sixteen four-bit input patterns, ordered transaction indices, registered
  inputs, NumPy packed integer scores, lowest-index class selection, counters,
  fixed clock/reset timing, post-update latency and the complete final drain.
  These are repeated evaluations of sixteen distinct patterns, not 64 distinct
  patterns or an exhaustive proof for the trained model.
- A fifth simulator case sends five identical all-zero inputs to a network
  with tied zero class scores. It verifies that five separate transactions are
  recorded and that every predicted class is zero despite no changing image
  data. The transaction count is independent of signal-transition count.
- Five fault cases independently corrupt the event ledger and verify rejection
  of missing entries, duplicate indices, altered cadence, altered latency and
  completion before outputs drain.

The root's final full-suite run including these ten cases passed **95 tests in
10.83 seconds, with no skips**. This is the root's reported run, distinct from
my independent targeted run; the ten cases are already included in 95.

## Independent full trained-model capture

I separately executed the full capture command:

```bash
.venv/bin/python scripts/capture_baseline_waveform.py runs/digits_w1000 \
  --export runs/digits_w1000/uart_comb_head \
  --implementation runs/digits_w1000/uart_comb_head/implementation.UVAx2g
```

Independent result:
`runs/digits_w1000/baseline-waveform.q2umneq1/result.json`.
Primary result:
`runs/digits_w1000/baseline-waveform.xs90rtvt/result.json`.

For **each** attempt I independently checked all **13 source hashes**, **16
saved-artifact hashes** and **two simulator executable hashes** against disk.
The archived input array is identical to the saved 450-row source array, and
`input_indices.json` is exactly 0 through 449. The captured inference source is
byte-identical to the feasible head-only board export.

Using a separate test-side VCD decoder, I checked the actual recorded values
rather than relying only on the simulator's PASS line or CSV ledger:

- Every one of the 450 rising-edge input words and input-register values
  equals its corresponding saved row, in order.
- Every one of the 450 post-update valid output words equals the packed NumPy
  integer scores, and its class equals NumPy's lowest-index argmax.
- Input/output indices and counters advance exactly once per transaction.
- Reset is asserted through the initial three cycles, and all 457 recorded
  rising edges have the fixed 83,334 ps cadence.
- The final input remains held throughout drain. The completion marker occurs
  on the third falling edge after the final output check, both valid signals
  are low, and the final VCD timestamp is one tick after completion.

Both fresh attempts agree on these boundaries:

| Boundary | Timestamp |
|---|---:|
| First input capture | 291,669 ps |
| Last input capture | 37,708,635 ps |
| First output check | 458,338 ps |
| Last output check | 37,875,304 ps |
| Capture-done marker | 38,083,638 ps |
| Final VCD timestamp | 38,083,639 ps |

Each trace is 6,476,465 bytes. Whole-VCD hashes need not match between fresh
runs because VCD headers can contain run metadata. Each attempt's individual
hash remains checked against its own manifest.

The independent audit and summary are preserved in
`baseline-waveform.q2umneq1/independent-verification.py` and
`independent-verification.json`. Reproduce the separate provenance and trace
audit with:

```bash
.venv/bin/python runs/digits_w1000/baseline-waveform.q2umneq1/independent-verification.py
```

The tracked test file contains the separate decoder and transaction checks.
The raw audit imports that file and records its hash, so the verifier itself
has provenance. These files and both raw captures remain local and gitignored;
a fresh clone needs the historical artifacts or reproduced full runs. The
small synthetic regression cases are self-contained.

## Research assessment and limits

This step establishes a reproducible **zero-delay RTL capture** of a particular
historical model under a particular fully occupied standalone-core workload.
It is useful groundwork for checking whether a training-time switching proxy
predicts actual settled logical changes or mapped activity.

The trace includes reset, pipeline fill and drain. Its entire duration must not
be used automatically as a useful-work denominator; step 3.5 still needs an
explicit analysis window. UART throughput and board-level power remain a
different workload. No transition totals, alias-aware sums, unknown-value
transition handling, per-category activity or settled-layer/Python switching
agreement are claimed by this review.

The historical digits test set has already been inspected and remains
exploratory. Later control and penalty runs need matched partitions, target,
architecture, clock, input order and workload, validation-based selection and
repeated seeds. Gray coding remains a separate experiment. Recording this
trace establishes neither a regularizer benefit nor research novelty. Fewer
logical transitions alone would not establish lower energy; mapped/power
analysis or electrical measurements are still needed.

No test or simulation failure required a debugging fix during this review, and
no implementation correction was needed before this verdict.
