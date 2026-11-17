# Step 3.9 independent verification

Review status: **method and evidence verified (Nov 16); no blocking finding.**
Five non-blocking wording/labeling findings are listed below for the author.

## Scope

The question is narrow. Does the step 3.9 capture apply the routed design's
nextpnr SDF delays to the archived, validated head-only UART board, and count
per-net timed transitions and settled changes correctly? Is
`extra = timed transitions − settled changes` a sound glitch estimate under
Icarus's delay model, and are the claims bounded by that evidence?

Reviewed:

- `scripts/capture_timed_activity.py`
- `tests/test_timed_activity.py`
- [3.9 walkthrough](../steps/3.9-assess-glitch-activity.md)
- [tracked summary](../results/step-3.9-timed-activity.json)
- evidence `runs/step3.9-glitch/timed-activity.0hvnej44/`
- archive `runs/digits_w1000/uart_comb_head/implementation.UVAx2g/`

The 5-minute capture was not rerun. The independent scripts are in
`runs/step3.9-verify/`.

## Method and results

1. **Bitstream and renaming.**
   - The re-routed `routed_uart.asc` and `routed_uart.json` are byte-identical
     to the archived ones (SHA-256 `dcbc3c66…` and `c9b8cc84…`). The archive
     status is `validated_route_passed`.
   - `check_rename.py` independently rebuilds the sorted `cN` mapping from
     `routed_uart.json`. It then un-escapes every name in `routed.sdf` and
     compares the two SDF files line by line.
     - All 4,169 INSTANCE and 13,871 INTERCONNECT lines map. No other line
       differs, and no backslash remains in the SDF.
     - Every routed cell has an SDF instance.
     - `renamed.json` cells, ports and netnames equal the originals.
     - All 4,169 Verilog instances are named `cN`.
   - `arcs.py` counts driver-pin to load-pin arcs in the netlist: 13,871.
     This equals the SDF arc set exactly, so no routing arc is missing.
   - Escaped *wire* names remain in `renamed.v`. Icarus accepts them, so this
     is harmless.
2. **Delays are applied.**
   - `sim_timed.log` contains only `TIMINGCHECK not supported` warnings, plus
     PASS and `$finish`. `build_timed.log` contains only "Choosing typ
     expression" and "Timing checks are not supported".
   - `-DTIMING` enables zero-default specify blocks for `ICESTORM_LC`, `SB_IO`
     and `SB_GB`, which are all the cell types in the design. The SDF has no
     SB_IO IOPATH, so I/O cells keep zero cell delay.
   - A separate 4,800-clock timed simulation (`gen_delay_tb.py`,
     `check_delays2.py`) sent 4 UART bytes and logged pins. Every observed
     transition was compared against the SDF:

     | Check | Result |
     |---|---|
     | Flip-flop CLK→O | 14,835/14,835 exact |
     | Sampled LUT I→O changes | 144/144 exact |
     | Carry CIN/I1/I2→COUT changes | 21,221/21,221 exact |
     | Interconnect, 3,000 sampled arcs (O, COUT, GLOBAL_BUFFER_OUTPUT, D_IN_0) | 6,106,702 events at exactly source + SDF delay |

   - The remaining interconnect events are all swallowed pulses narrower than
     the arc delay, as leading/return-edge pairs (O: 80/80; COUT: 2,263/2,262,
     the extra one at simulation end). This independently confirms inertial
     filtering on interconnect.
3. **Counter semantics.**
   - Code reading confirms the following:
     - Samples fall 1 ps before each rising edge.
     - The window is (open sample, close sample].
     - Lazy commit is correct: the value at every boundary since a net's last
       event equals `pv`, and `FINAL` handles the last interval.
     - `=== 1'bx` separates X/Z-involving changes.
     - Shared `c`/`offset` temporaries are race-free in a single-threaded
       simulator.
   - Independent oracle (`counter_check.py`):
     - It builds the production testbench on `renamed.v` with SDF for 85 nets
       (the 40 largest-extra nets plus every 97th), runs a 3,000-cycle idle
       window and logs raw events.
     - Python then recomputes the transitions in the window and the
       sample-to-sample settled changes.
     - Result: 0 mismatches, 12,000 extra transitions exercised, 0 late events.
   - `recompute.py` rebuilds every category and total in `result.json` from
     `counts_*.txt` and `net-ledger.json`, and finds exact agreement.
     - Timed and untimed settled counts are equal for all 4,323 nets.
     - All nets have zero unknowns, and every extra count is even and
       non-negative.
   - The 2 clock nets have 651,360 = 2 × 325,680 edges and are correctly
     excluded.
   - The latest event, at 51,369 ps, is well outside the 10 ns guard band.
   - `extra` is a valid count of there-and-back hazard pairs per *driver net*
     (counted at the driver output pin, not per sink), under Icarus's
     inertial model.
4. **Category heuristic.**
   - It is name-prefix based. No core net also carries a non-core `board.*`
     name. However, 3,025 of 3,252 core nets have only Yosys-derived names.
   - Four "core" nets named `board.adapter.core.out_valid_SB_LUT4_*` behave
     like adapter reply/control logic (95–384 settled changes each, against at
     most about 7 for real core logic). They hold 895 of 12,178 core settled
     changes (7%) and 0 extra. Reclassifying them would raise the core ratio
     from 1.68 to about 1.81. The qualitative conclusion is unchanged.
5. **Evidence integrity.** The `result.json` hash matches the tracked summary.
   All 24 `files_sha256` entries and all source hashes match the files on
   disk. The tracked summary equals `result.json` on categories, totals,
   window, counts and bitstream.
6. **Tests:** `.venv/bin/python -m pytest tests -q` → **254 passed in
   14.30 s, no skips**. This includes 9 tests from `test_timed_activity.py`
   and the untracked `test_switching_metrics.py`.

## Non-blocking findings (wording/labels)

- **F1:** "unclassified (nextpnr-inserted)" also contains the `button_n` reset
  chain, `uart_tx_pin` logic, `$PACKER_VCC_NET` and the carry feed-in LCs of
  interface counters. Its roughly 529k settled changes are effectively
  interface activity. Relabel it, for example "unclassified (board-level /
  nextpnr-inserted)".
- **F2:** The Evidence section says "4,321 net bits". `result.json` observed
  4,323, including 2 clock nets.
- **F3:** "Just under the 51.584 ns worst path" compares a testbench-edge to
  driver-pin offset with an FF-to-FF STA path that includes setup and clock
  insertion. It is a plausibility check, not a match.
- **F4:** The sentence "3.7/3.8 would undercount by about 2.7×" should be
  scoped. Those steps used a different netlist, net population and workload
  (the standalone core with 450 streamed images). The factor applies to this
  routed design's own settled count over 8 images and depends on the inertial
  model. Also note the 4 adapter nets in core (finding 4 above).
- **F5:** The inertial probe figures (200/50/800 ps) are not archived or
  tested. The swallowed pulses measured here support the behavior
  qualitatively, but those specific numbers are not reproducible from the
  repo.

## Verdict

**Pass.** Delays are demonstrably applied from the SDF. Renaming is complete.
The bitstream is the validated one. The counters agree with an independent
raw-event oracle, and the totals recompute exactly. The limits stated in the
walkthrough are:

- inertial filtering
- a single corner
- the UART board rather than the standalone core
- 8 images
- not energy

These are appropriate. Address F1–F5 in wording; none of them changes the
measured numbers.
