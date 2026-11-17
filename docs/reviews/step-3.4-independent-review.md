# Step 3.4 independent verification

Reviewed November 16, 2026 by the independent `verify_step_3_4` agent using
the engineering code-review skill.

## Verdict

**No blocking finding remains for the supported digital VCD counter and
capture-bound diagnostic report.** Step 3.4 may be marked complete. This
verifies counting machinery; it does not approve a useful-work measurement
window, classify signal activity or establish network energy savings.

## Code and methodology review

I reviewed [vcd_activity.py](../../dlgn/vcd_activity.py),
[analyze_waveform.py](../../scripts/analyze_waveform.py), the
[walkthrough](../steps/3.4-count-waveform-transitions.md),
[tracked summary](../results/step-3.4-waveform-activity.json), and the
preserved step 3.3 captures.

- Each VCD identifier has one state and one counter regardless of alias count.
  Alias declarations preserve hierarchy, range, type and width; incompatible
  widths are rejected. Distinct identifiers with equal values stay distinct.
- Initial observations never become toggles. Bit masks retain separate one,
  X and Z states. Known zero/one flips are counted separately from changed
  bits involving unknown states, including X-to-Z changes.
- Known short vectors zero-extend; leading X/Z extends the unknown state.
  Uppercase values normalize consistently. Width overflow and invalid values
  are rejected rather than truncated or coerced.
- The parser follows file order, including multiple events at one timestamp.
  Repeated normalized values are redundant records. It does not silently
  collapse events to a settled snapshot or label them physical glitches.
- Window mechanics use `(start,end]` with state carried through excluded
  records. An explicit start zero excludes time-zero observations, while an
  omitted start includes their initialization statistics. Malformed trailing
  data is rejected even beyond a requested end boundary.
- The supported format is deliberately digital. Unsupported real/string/event
  encodings and dumping suspension fail explicitly. A complete general-purpose
  VCD implementation is not claimed.
- The wrapper creates fresh analysis folders, checks all artifact hashes
  supplied by the passed capture manifest, checks VCD/manifest stability,
  and archives the exact manifest and analyzer sources. It reads existing
  capture evidence; it does not claim a fresh RTL simulation.
- Failed attempts retain a failed report. The original trace, archived model,
  ordered inputs, clock and earlier reports are not rewritten.

Range-qualified path strings such as `top.bus[3:0]` and exact decimal-string
`seconds_per_tick` metadata are intentional schema choices. Integer timestamps
and the declared timescale remain authoritative.

## Independent regression tests

I authored [test_vcd_activity.py](../../tests/test_vcd_activity.py).
The targeted run passed **35 tests in 0.07 seconds, no skips**:

```bash
.venv/bin/python -m pytest tests/test_vcd_activity.py -q
```

The cases include:

- A hand-counted mixed trace with true aliases, same-timestamp updates,
  redundancy, short vectors and X/Z changes: **10 known bit toggles**
  (8 rises, 2 falls), **9 unknown-involving changed bits**, and **19 total
  four-state changed bits**. It also checks 12 records, 2 initializations,
  8 changed-value records and 2 redundant records.
- Four carried-state boundary cases; six invalid or outside-trace window
  cases; unknown initialization and extension; multiline headers and multiple
  records per line; and distinct IDs with equal values.
- Ten malformed/unsupported trace cases plus explicit checks for malformed
  records after an early end window, scalar records for vectors and duplicate
  hierarchical declarations.
- A `0 → X → 1` case that counts zero known binary flips, and a dumpall case
  that preserves repeated unknown snapshots without inventing transitions.
- A hash-bound synthetic archive showing immutable capture files and exact
  manifest/source copies; four corrupted-archive cases; and a concurrent
  manifest-change case. All failures retain failed analysis reports.

The root's final full suite passed **130 tests in 10.16 seconds, no skips**.
This is the root's reported run, separate from my targeted run. These 35 cases
are included in 130, not additional unique tests beyond it.

## Independent full-trace analysis and oracle

I separately ran `analyze_capture` on both previously verified 450-image
captures, producing fresh reports:

- `runs/digits_w1000/baseline-waveform.xs90rtvt/activity-analysis.57c50ob3/result.json`
- `runs/digits_w1000/baseline-waveform.q2umneq1/activity-analysis.hhsciw9w/result.json`

The root's separate primary analysis is
`baseline-waveform.xs90rtvt/activity-analysis.zemyttyn/result.json`.

My independent oracle compares four-state strings one bit at a time, rather
than using the production parser's integer masks. For **every one of the 1,036
identifiers**, the known flips, rises, falls, unknown-involving changes and
all four-state changes agree in all three analysis reports. The aggregate
transition counters independently agree:

| Whole-trace diagnostic | Count |
|---|---:|
| Known 0/1 bit toggles | 1,843,155 |
| Rises / falls | 921,584 / 921,571 |
| Changed bits involving X/Z | 10,897 |
| All four-state changed bits | 1,854,052 |

The reports also record 379,907 value observations, 1,036 initializations,
325,603 changed-value records and 53,268 redundant records. These satisfy the
record-accounting invariant. There are 10,897 unknown initial bits and 1,023
value records containing unknown bits.

For each analyzed archive I verified all **16 capture-artifact hashes**, the
capture-report hash, all **three saved analysis-artifact hashes**, and both
current analyzer source hashes. The copied capture manifest is byte-identical
to its original. This is read-only reanalysis of existing capture evidence;
no earlier capture was relabeled as a new simulation.

The independent audit script and results are preserved under
`activity-analysis.57c50ob3/independent-verification.py` and
`independent-verification.json`. Reproduce the oracle/provenance audit with:

```bash
.venv/bin/python runs/digits_w1000/baseline-waveform.xs90rtvt/activity-analysis.57c50ob3/independent-verification.py
```

The audit imports the test file's separate string oracle and records/checks
that file's hash. It checks all three analysis reports and their referenced
artifacts. Raw runs remain local and gitignored; synthetic regression tests
remain self-contained.

## Initial schema mismatch and correction

The first test draft assumed alias paths without declared ranges and a numeric
time conversion. The implementation deliberately supplied range-qualified
paths and an exact decimal string. The initial run had 22 passing cases and
two failed metadata assertions; the hand-counted transition results already
agreed. The expectations were corrected to the documented schema, then all
24 initial cases and the expanded 35-case suite passed.

No counting rule, input window or unknown/alias policy was weakened. The
expected/actual observations and reproduction command are retained in
`runs/step-3.4-debug/initial-test-observations.txt`, labeled as an excerpt/summary,
and in the walkthrough's debugging record. Retaining explicit metadata-schema
assertions prevents this assumption mismatch from recurring.

## Research assessment and limitations

The full trace has **1,036 declarations and 1,036 identifiers**, with no true
VCD aliases; alias deduplication is demonstrated by the synthetic fixtures.
Logical copies such as `lN` and `lN_c` can use distinct identifiers and both
contribute to the raw sum. A unique VCD identifier is not proof of a unique
physical net or unique logical gate output.

Consequently **1,843,155 is only a raw whole-trace diagnostic**, including
clock/control, testbench markers/counters, duplicated logical representations,
reset, startup and drain. It must not be presented as the validated network
switching total, compared directly with Python's settled changes per gate per
image transition, or used as an energy metric.

Step 3.5 must choose equivalent useful-work windows; 3.6 must separate activity
categories; 3.7 must compare aligned settled logical outputs with NumPy.
Mapped activity and physical glitches need their own supported evidence.
No time-normalized or per-prediction rate is established by this review.

The direction remains conditional on matched target, architecture, clock,
partition, image order and workload, validation-based selection and repeated
seeds. The historical digits pool remains exploratory. Counter correctness is
useful infrastructure, but it demonstrates neither regularizer effectiveness
nor novelty. No power estimate, measured power or energy saving exists here;
fewer recorded digital transitions alone would not establish lower energy.
