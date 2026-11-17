# Step 3.6 independent verification

Reviewed November 16, 2026 by the independent `verify_step_3_6` agent using
the engineering code-review skill.

## Verdict

**No blocking finding identified.** Step 3.6 is verified for categorized RTL
observations and frame-aligned settled counting under the fixed capture
protocol. This does not approve logical-layer values against NumPy (step 3.7),
mapped physical-node activity, physical glitches, power, energy or novelty.

## Code and methodology

I reviewed [report_activity_categories.py](../../scripts/report_activity_categories.py),
the exporter, window validator, raw counter, archived RTL/parameters and the
[walkthrough](../steps/3.6-separate-activity-categories.md). The report verifies
capture hashes and exact supported exporter structure before assigning roles.
Every observed ID belongs to one whole-trace category. All counter fields and
identifier counts reconcile; true aliases are counted once, while distinct IDs
are retained even if their values agree. Ambiguous role aliases and unclassified
DUT observations fail explicitly.

The learned-network metric selects only `l1_c`–`lD_c`. Unregistered forwarding
copies, layer registers, input/output ports, the score bank, output logic,
clock/control and simulation bookkeeping do not enlarge that denominator.
Roles follow architecture, rather than the VCD `reg` keyword. In particular,
`sc_flat` is an observable packed view of the head score bank when enabled,
not another physical register bank. The capture does not separately expose
unpacked `sc`/`sc_reg` arrays, so this is not a complete storage inventory.

Per-observation raw events and settled endpoint changes remain separate.
Staggered stage windows preserve the same neighboring-image pairs and cannot
be added into one common physical-time energy interval. Whole-trace category
sums are a diagnostic reconciliation, not a unique physical-net total.

## Independent regressions

Added [20 independent cases](../../tests/test_activity_categories.py):

- Four fresh toy Icarus captures cover every layer/head register configuration.
  A separate line-based decoder and string-per-bit event oracle check each
  observation's settled counts, raw known/unknown changes, category ownership,
  identifier coverage and reconciliation.
- Repeated frames retain 15 neighboring-image pairs with zero settled data
  changes while the clock continues switching.
- Restored intermediate known and X pulses on a layer bus leave settled
  counts unchanged while increasing raw known or unknown-involving events.
  This verifies that endpoint sampling does not erase recorded intermediate
  behavior or mislabel it as physical glitches.
- True aliases count once; distinct-ID equal-count layer views remain separate.
  Conflicting clock/register and combinational/registered aliases fail.
- Unclassified scopes/names, changed artifact hashes, rebound-hash changed RTL,
  missing manifest evidence and rebound-hash malformed ledgers fail. Report
  failures remain in fresh attempt folders.

Command:

```bash
.venv/bin/python -m pytest tests/test_activity_categories.py -q
```

The final independent run passed **20 tests in 0.92 seconds**, no skips. The
root reports **172 full-suite tests passed in 12.25 seconds**, no skips; that
run is separate from my focused run. No test failure or production correction
was necessary during this review. `git diff --check` passed.

## Full-capture reruns and independent audit

I created fresh read-only analyses of both existing step 3.3 captures:

- `runs/digits_w1000/baseline-waveform.xs90rtvt/activity-categories.y98xlian/result.json`
- `runs/digits_w1000/baseline-waveform.q2umneq1/activity-categories.z_xyxdti/result.json`

The independent audit also checks the root's primary report:
`baseline-waveform.xs90rtvt/activity-categories.w0799sk1/result.json` under the
same historical run. All three reports pass the separate event and endpoint
oracles. Each has **1,036 IDs, 1,036 declarations, 14 aligned observations,
16 capture hashes, eight current source hashes and nine saved analysis artifact
hashes** checked, plus the capture-manifest hash and exact saved manifest copy.
Test/oracle file hashes are pinned by the audit.

All reports agree on 1,843,155 whole-trace known bit flips and 10,897
unknown-involving changes across the categorized diagnostic. Canonical settled
layer counts are 126,546, 144,016, 167,436 and 190,171, respectively. Their
**628,169 changes / 1,796,000 bit-pair opportunities = 0.34976002227171493**
is a logical comparison metric over 4,000 gate slots and 449 image pairs.
The aligned raw counts equal these settled counts for this specific trace,
with zero unknown-involving layer changes in those windows. This equality
does not establish physical glitch behavior.

Audit evidence is preserved under the first independent report:
`activity-categories.y98xlian/independent-verification.{py,json}`. Reproduce:

```bash
.venv/bin/python \
  runs/digits_w1000/baseline-waveform.xs90rtvt/activity-categories.y98xlian/independent-verification.py
```

The audit reads archived traces; it does not claim fresh simulation or FPGA
implementation. These local artifacts remain gitignored, so a fresh clone
needs their archive or reproduced captures. The toy regressions are self-contained.

## Bounded research assessment

Tested correctness covers observable RTL category accounting and settled
endpoint counting for the supported matched workload. This gives a useful
switching proxy, not measured capacitance-weighted activity or energy. Direct
NumPy layer-state/transition agreement still requires step 3.7. Mapped activity,
timing-aware glitch evidence, device power analysis and electrical measurements
remain separate work.

There is no demonstrated regularizer benefit, lower power/energy or verified
novelty. Keep architecture, target, clock, data splits and sequence matched in
future comparisons; choose training settings on validation data. The historical
inspected digits test remains exploratory.
