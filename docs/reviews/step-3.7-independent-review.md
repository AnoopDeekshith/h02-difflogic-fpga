# Step 3.7 independent verification

Reviewed November 16, 2026 by the independent `verify_step_3_7` agent using
the engineering code-review skill. The engineering debugging skill was also
used for an incorrect test-fixture assumption described below.

## Verdict

**No blocking production finding remains.** Step 3.7 is verified for exact
settled layer values, adjacent-image transition masks and per-gate changes
under the supported archived workload. Scores and classes also match, including
lowest-index ties. This is sampled RTL correctness and a logical switching
proxy, not formal equivalence, mapped activity, physical glitches or energy.

## Methodology and implementation

I reviewed [compare_activity_numpy.py](../../scripts/compare_activity_numpy.py),
the NumPy reference, exporter, window validator, raw counter, archived inputs
and [walkthrough](../steps/3.7-cross-check-numpy-and-rtl-activity.md).

The checker verifies capture hashes and the exact supported exporter structure,
checks binary input shape and input/reference hex order, and recomputes layer
states and scores using the NumPy reference. The same images and stage-aligned
windows retain all image pairs. Column `j` maps to Verilog bit `j`, with score
class `k` starting at bit `k × SW`. The scalar oracle independently verifies
this ordering and lowest-index selection on ties.

Every observed settled value is compared before any aggregate result is
accepted. Exact pairwise changing-bit masks and per-gate counts are checked,
so equal aggregate counts cannot hide wrong gate states. Forwarding copies
and pipeline/output registers are checked but excluded from the canonical
`l1_c`–`lD_c` learned-gate denominator. Unknown sampled states fail explicitly.
Raw known and unknown-involving events remain separate from settled changes.
The report preserves source/manifest copies, full settled sequences and
mismatch evidence, then rechecks artifact/source stability before success.

## Independent regressions

Added [22 independent cases](../../tests/test_activity_numpy.py):

- Fresh Icarus toy captures exercise all four layer/head register configurations.
  A scalar truth-table evaluator, explicit numbered-bit packing, independent
  line-based VCD decoder and string-per-bit raw-event oracle check values,
  changing bits, per-gate counts, metadata and provenance. The scalar evaluator
  does not call the production NumPy forward/scores/predict or packing code.
- One-hot values across byte boundaries test numbered-bit serialization,
  including a 17-bit width. Repeated frames retain all 15 image pairs with zero
  settled changes. A separately constructed constant-zero final layer creates
  16 deliberate score ties and requires class 0 after a fresh Icarus rebuild.
- Complementing one sampled bit on every image preserves the aggregate toggle
  count and pair masks while changing every state. The report rejects it and
  preserves exact image/bit mismatch evidence. Corrupt forwarding-copy and
  registered-layer samples also fail even when canonical observations match.
- Restored known and X pulses between samples leave the NumPy/settled result
  matched while increasing raw known or unknown-involving events. Neither is
  represented as physical glitch evidence.
- Rebound-hash NumPy order/nonbinary inputs, score/class references, sampled X,
  row order, ledger and exporter faults, missing evidence and stale hashes fail.
  Every rejection retains its fresh failed report.

Command:

```bash
.venv/bin/python -m pytest tests/test_activity_numpy.py -q
```

Final independent focused run: **22 passed in 1.35 seconds, no skips**. The
root separately reports **194 full-suite tests passed in 13.83 seconds, no
skips**. Those 22 cases are included in 194, not additional tests beyond it.
No production change was necessary during review. `git diff --check` passed.

## Fixture failure, correction and independent recheck

**Expected versus actual:** the initial repeated-input test assumed all 16
images had tied scores. The checker and separate scalar/VCD oracle instead
agreed on zero tied images and zero settled changes. The initial suite had
20 passing cases and one failed assertion, `assert 0 == 16`, in 1.31 seconds.

**Root cause:** repeated inputs guarantee repeated outputs, but not equal
scores across classes. Random layer connections and the existing gate rules
did not provide the assumed tie. This was a test expectation error; there
was no NumPy/RTL discrepancy or production correction.

**Preserved evidence and exact reproduction:**
`runs/step-3.7-verifier-debug/repeated-fixture-tie-assumption/` contains the
exact initial test source, original capture/comparison evidence, initial
observations/output summary, and corrected-verification JSON. The archived
test was independently rerun to confirm the original assertion still fails:

```bash
PYTHONPATH=tests:scripts:. .venv/bin/python -m pytest \
  runs/step-3.7-verifier-debug/repeated-fixture-tie-assumption/initial-test_activity_numpy.py \
  -q -k repeated_zero
```

The exact command/environment/return code and complete reproduction output are
saved as `archived-exact-reproduction.{json,txt}` in that folder. This is the
expected failure of the preserved old test, not a new production failure.

**Fix, verification and prevention:** retain the repeated-input zero-change
test and introduce a separate explicit tied-score fixture whose final layer
is constant zero. That fixture is freshly rebuilt and simulated before its
hashes are recorded; every class score is zero and class 0 wins for all 16
images. The corrected suite passes all 22 cases. Keep constancy and tie tests
separate so future changes cannot depend on accidental random-fixture ties.

## Full-capture analyses and separate audit

Fresh independent read-only comparison reports:

- `runs/digits_w1000/baseline-waveform.xs90rtvt/activity-numpy.vsauy9f4/result.json`
- `runs/digits_w1000/baseline-waveform.q2umneq1/activity-numpy.e5oitt9n/result.json`

I also audited the primary report
`baseline-waveform.xs90rtvt/activity-numpy.e4k0xtre/result.json` under the same
historical run. All three pass the separate scalar-reference, line-decoded
sample/state/transition and string-per-bit event oracles. Each report has
**16 capture hashes, eight current source hashes and ten saved analysis
artifact hashes**, including `settled-values.json`, verified. Exact saved
manifest identity is checked. The audit pins the three independent test/oracle
file hashes and records each result hash.

All 14 observations match for 450 images: zero sampled-state, transition-mask
or per-gate count discrepancies. This includes **3,839,400 sampled bit
comparisons and 3,830,868 transition-bit comparisons**, which include copies
and interfaces and are verification work, not unique physical gates. The six
historical images with tied maximum scores preserve the lowest class index.

Canonical layer changes match independently: **126,546; 144,016; 167,436;
190,171**. Their **628,169 / 1,796,000 = 0.34976002227171493 changes per gate
per image pair**, with 314,079 rises and 314,090 falls, also equals a fresh
`hard.toggle_rate` evaluation of the original step 3.1 software metric.
The aligned raw-event counts equal settled counts for these observations,
with zero unknown-involving changes in their windows. Whole-file diagnostics
include a different signal population and startup interval and are not the
same measurement.

Audit files are under the first independent report:
`activity-numpy.vsauy9f4/independent-verification.{py,json}`. Reproduce from
the repository root:

```bash
.venv/bin/python \
  runs/digits_w1000/baseline-waveform.xs90rtvt/activity-numpy.vsauy9f4/independent-verification.py
```

These are fresh analyses of preserved simulations, not new simulation or FPGA
implementation runs. Raw artifacts remain local and gitignored; a fresh clone
needs their archive or reproduced captures. Toy regressions are self-contained.

## Bounded research assessment

Tested correctness covers this exact supplied workload and supported register
schedules. NumPy and zero-delay RTL agree on settled logical states and
activity; this does not establish physical glitch behavior, mapped net
capacitances, power or energy. Stage-aligned image-pair windows are staggered
in physical time and cannot be summed into a common device-energy interval.

There is no demonstrated regularizer benefit, lower energy or verified novelty.
Continue with mapped activity and complementary metrics, keeping target,
architecture, clock, splits and input order matched. Select future training
settings on validation data. The already inspected historical digits test
remains exploratory.
