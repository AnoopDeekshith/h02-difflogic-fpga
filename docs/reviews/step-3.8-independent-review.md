# Step 3.8 independent verification

Review status: **code and measurement verified (Nov 16); no blocking finding.**
The step 3.8 walkthrough still needs its evidence/reproduction sections filled.

## Scope and method

The bounded question is whether a fresh standalone head-pipelined core, mapped
by Yosys to iCE40 UltraPlus primitives, computes the archived NumPy reference
scores/classes and records activity on every unique numeric net bit connected
to a top-level or primitive port. This does not establish routed timing, physical
switching or energy. The synthesis explicitly selects `-device u`; it is a new
mapping protocol, distinct from the historical board implementation.

Numeric Yosys bit identity defines the counting population. A net with several
bus names or cell-pin aliases is counted once; constants and stale unattached
netnames are excluded. Every included bit needs exactly one recognized driver.
The independent oracle derives this union directly from raw `mapped.json` ports
and cell connections (3,569 bits, identical to `net-ledger.json` order), then
decodes canonical VCD bus events as strings, one bit at a time. It does not call
the production VCD parser or mapped counter.

The complete-burst diagnostic uses one interval, `(first input drive − 1 ps,
last output check]`, so it includes input setup, pipeline fill and final useful
output. The whole-trace diagnostic additionally contains reset and drain. Neither
window is a gate-pair denominator or a physical energy measurement. Clock is one
observed logical net, not a capacitance-weighted clock-tree model.

The installed Yosys `cells_sim.v` initializes flip-flop Q to zero. Startup semantics
therefore differ from uninitialized behavioral RTL; raw unknowns and initialization
must be reported honestly. Functional zero-delay primitive simulation does not
establish timing-aware glitch activity. Icarus writes each VCD identifier at most
once per timestamp, so zero-delay intermediate pulses never reach the file and
the counts are settled per-timestamp changes, not glitch evidence.

## Initial debugging finding

Reproduction: `.venv/bin/python -m pytest tests/test_mapped_activity.py -q`.
Expected: malformed mapped primitive pin names, multi-bit scalar pins and invalid
constant string `"2"` must be rejected. Actual initial result: **3 failed, 12 passed
in 0.24 s**. Each failing case was accepted instead of raising `ValueError`.

The root cause was incomplete schema validation in `instrument_json`: input port
names and widths were not checked, and every string was skipped as a constant.
The independent tests isolated these three defects; alias deduplication, driver
conflicts and the separate four-state event oracle already passed. The finding is
preserved in `runs/step3.8-independent/initial-test-findings.txt`. All three are
fixed (`unknown_input_port`, `wrong_width`, `nonbinary_constant`) and now pass.
These mutation regressions are the prevention check.

## Re-verification after code-review fixes

- Fix 1: `count_activity` reports `max_bus_records_per_tick`; real trace value 1.
  Independent scan of `mapped.vcd`: no identifier (any signal) has more than one
  record in any timestamp.
- Fix 2: source hashes taken before copying, copies checked, rechecked at end;
  all ten recorded hashes match current files; run-folder testbench matches.
- Fix 3: `yosys-config`/`vvp` resolved beside `yosys`/`iverilog`
  (`Cellar/yosys/0.63`, `Cellar/icarus-verilog/13.0`).
- Fix 4: window start at/after last trace tick is rejected (tested).
- Fix 5: categories clock 1, control 2, data_input 192 bits; clock 914 toggles =
  2 x 457 edges; control 1 rise / 2 falls matches reset and `in_valid` schedule.
- Fix 6: scalar widths always checked; full widths via `port_widths` (tested).
- Fix 7: `capture_baseline_waveform` rejects non-0/1 inputs (`np.isin`); no
  dedicated test in `test_baseline_waveform.py` (non-blocking).

Fresh capture `runs/digits_w1000/mapped-activity.57fn0ze0/`: 450/450 mapped
scores/classes pass. Independent per-bit oracle matches all 3,569 bits for both
windows; categories sum to totals: whole trace 667,463 known flips (LUT 569,566,
FF 51,053, carry 23,856, data input 22,071, clock 914, control 3), burst
(250001, 37875304] 667,290; zero unknown. Verifier's fresh reanalysis
`mapped-analysis.s8y33n7i/` passed and equals the recorded activity.
Full suite: 239 passed, no skips.

Non-blocking: `validate_port_bus` docstring/`rule` string (scripts/mapped_activity.py
263-264, 329) still say several events may occur per timestamp; the recorded
`yosys-config` "version" is the echoed literal `--version` (path and hash are the
real provenance).

## Research-direction assessment

- Tested correctness: exact scores/classes for 450 saved inputs, full input/port
  schedule, primitive coverage, independent per-bit activity and provenance
  verified. Not formal equivalence over all inputs.
- Measurement proxy: unique mapped digital net-bit changes in an explicitly
  defined simulation workload; gate-count and net-count metrics have different
  populations and cannot be treated as interchangeable energy measures.
- Actual power/energy evidence: none. No electrical rail measurement, device power
  estimator, capacitance weighting or routed-delay simulation is performed.
- Novelty: not established. This work improves measurement infrastructure; it does
  not demonstrate that a training penalty saves energy or is a new research method.
