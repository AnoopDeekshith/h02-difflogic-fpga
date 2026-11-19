# Step 4.11 (part 1) independent review: board-activity ranking

Reviewer: independent verification sub-agent, Nov 19, 2026.
Scope: `scripts/rank_board_activity.py` and its output
`docs/results/step-4.11-board-activity-ranking.json`, computed from the archived
step 3.9 SDF-timed routed UART-board capture
`runs/step3.9-glitch/timed-activity.0hvnej44/`. This is read-only analysis.
No simulation was run and no tracked file was edited. Scratch files are in
`runs/step4.11-review.independent/`: `structural_rank.py`, `structural_rank.out`,
`structural_blocks.json` and `rerun.json`.

**Verdict: the headline numbers reproduce. There is one BLOCKING finding, and it
concerns the wording of the professor summary, not the computation.** Candidate
statement (c), "prescaling idle_count removes most of its activity", is not
supported as worded. It must be reworded or dropped before it goes into the
summary. The script misses three RX-timer register bits, but the corrected
figures leave every rounded claim unchanged.

## 1. Provenance and reproduction

| Check | Result |
|---|---|
| Input hashes | `net-ledger.json` `69b09e83…`, `counts_timed.txt` `9e5c2998…` and `result.json` `e40c5901…` equal the values recorded in the JSON |
| Rerun | `scripts/rank_board_activity.py` rerun to scratch produces output **byte-identical** to the tracked JSON |
| Count file | 4,323 rows, indices 0..4322 in ledger order; the header reports 325,680 samples, 0 late events and 8 replies |
| Unknowns | timed-unknown and settled-unknown columns sum to **0** (the script does not check this; see N5) |
| Totals | **4,789,099** timed transitions and 2,265,499 settled changes. 3.9's `result.json` gives 3,486,379 excluding the clock, plus 1,302,720 for the clock, which equals 4,789,099 |

## 2. Independent structural re-classification (claim 1)

`structural_rank.py` does not reuse the script's name heuristic. From
`renamed.json` it treats a flip-flop as an LC with `DFF_ENABLE=1`. Counter
flip-flops are identified by their Q-net names. Next-state logic is the backward
combinational cone of a counter's flip-flops. The cone stops at flip-flops, IO
cells, global buffers and the constant nets `$PACKER_VCC_NET`/`GND`. A net is
assigned to a counter only if it lies in that counter's cone and in no other
register's cone. Nets that appear in more than one cone are reported as shared.

**Unnamed RX timer bits.** The RX timer is `$clog2(104)` = 7 bits wide. Only bits
0-3 keep their `receiver.timer[i]` names. Three flip-flops named
`receiver.state_SB_DFF_Q_D_SB_LUT4_O_I3_SB_LUT4_O_I3[0..2]` (c4006, c3998, c3999)
are bits 4-6, for three reasons:

- They share the timer's clock enable (c4009, `receiver.timer_SB_DFFESR_Q_E`).
- They sit at the end of the timer's carry chain c6→c4002→c4003→c4000→c3996→c3998→c4006.
- They feed back into themselves.

Their activity is 3,744, 7,904 and 12,064 transitions (23,712 in total). The
script puts them in `rx_other`.

**Carry-entry LCs.** I traced each of the three unclassified LCs:

| LC | Input I1 | COUT drives | Timed = settled | Equals |
|---|---|---|---:|---|
| c24 (`$nextpnr_ICESTORM_LC_5`) | `idle_count[0]` | c3458 (`idle_count[1]` FF) CIN | 208,000 | `idle_count[0]` toggles |
| c6 (`$nextpnr_ICESTORM_LC_0`) | `receiver.timer[0]` | c4002 (RX timer chain) CIN | 205,504 | `receiver.timer[0]` toggles |
| c26 (`$nextpnr_ICESTORM_LC_7`) | `transmitter.timer[0]` | c4152 (`transmitter.timer[1]` FF) CIN | 108,161 | `transmitter.timer[0]` toggles |

Each one feeds bit 0 into its counter's carry chain, so assigning them to the
counters is correct. Each COUT has a single sink on dedicated carry wiring.

**Block comparison.** Shares are of 4,789,099 timed transitions:

| Block | Script | Structural (this review) |
|---|---:|---:|
| Clock (2 nets) | 1,302,720 (27.20 %) | same |
| Core | 32,580 / settled 12,178 (0.68 %) | same (3.9 categories) |
| Counter register bits | 1,013,381 (21.16 %) | **1,037,093 (21.66 %)**: adds RX bits 4-6 |
| Counter next-state logic incl. carry entries | 1,726,551 + 521,665 = 2,248,216 (46.94 %) | 2,225,766 exclusive (46.48 %) + 100,770 shared with other registers (2.10 %) |
| All three counters | 3,261,597 (68.10 %) | 3,262,859 exclusive (68.13 %); 70.24 % incl. shared |
| idle_count, reg + logic + carry entry | 1,234,400 (25.78 %) | 1,234,848 (25.78 %); 26.07 % incl. shared |
| RX timer, logic + carry entry | 785,408 + 205,504 = 990,912 | 990,912 (identical) |

The name heuristic assigns very few nets to the wrong block. Apart from the
three RX bits, the only differences are:

- c4018.O, the idle_count reset/clear term (416 transitions)
- a few `receiver.state…` and `transmitter.timer_…_E` nets that the structural
  pass labels as shared (55,744, 14,561, 8,320 and smaller)

**Claim 1 is SUPPORTED.** The figures are 4,789,099 total, clock 27.2 %, core
0.7 % (32,580/12,178), and counters plus carry entries ≈ 68 %, about two-thirds.

## 3. When the counters run (claim 2)

The RTL (`rtl/dlgn_uart.sv`, `rtl/uart.sv`) behaves as follows:

- **idle_count.** It is 22 bits wide (`$clog2(3,000,000)`). It is cleared on
  `rx_valid` or whenever the state is not HEAD1/PAYLOAD, and it increments every
  clock otherwise. The timeout/error branch also clears it.
- **RX timer.** It counts down during START (51→0), DATA (8 × 104) and STOP (104).
  It is held in IDLE and RECOVER.
- **TX timer.** It counts whenever `!ready`, which covers 10 bit periods per byte.

**Testbench.** In `tb_timed.sv`, `send_byte` starts each byte at the negedge that
follows the previous stop bit, so the bytes of a request are back-to-back. The
next request starts 2 × 104 clocks after the full reply has been checked.

The counts match these rules exactly:

| Counter | Expected toggles of bit 0 | Measured | Active share of the 40,710 clocks per request |
|---|---|---:|---:|
| idle_count | 25 bytes (HEAD1 + PAYLOAD) × 1,040 × 8 = 208,000 | 208,000 | 63.9 % |
| RX timer | 26 bytes × (52 + 832 + 104 = 988) × 8 = 205,504 | 205,504 | 63.1 % |
| TX timer | 13 bytes × 1,040 × 8 = 108,160 | 108,161 (+1) | 33.2 % |

idle_count never counts past about 1,040 between bytes, so only bits 0-10 toggle;
bits 11-21 have zero transitions. Its register toggles total 416,000, exactly
2.0 per increment, as expected for a binary counter.

**Claim 2 is SUPPORTED.** One caveat: real host byte gaps within a request (USB
packetization) would lengthen idle_count's counting. The ideal back-to-back host
gives the minimum idle_count activity per request.

## 4. Candidate professor-summary statements

| | Statement | Verdict |
|---|---|---|
| a | Gray-coding pixels affects at most the input register (~3 %) plus downstream; core ~0.7 % of board | **Core 0.7 %: SUPPORTED. "At most input register…": NOT SUPPORTED as worded** (N1) |
| b | Gray counters could at best ~halve register-bit toggles (~21 % of board); effect on next-state/glitches (~47 %) unknown | **PLAUSIBLE-UNTESTED** (arithmetic supported) |
| c | Prescaling idle_count removes most of its activity (~26 %) | **NOT SUPPORTED as worded** (B1) |
| d | UART-bound: lower clock reduces clock and timer transitions per prediction ~proportionally | **Clock: SUPPORTED by arithmetic. Timers: PLAUSIBLE-UNTESTED** (N3) |
| e | Counts are not energy; clock capacitance far exceeds counter nets | **"Not energy / count share ≠ power share": SUPPORTED. Magnitude: PLAUSIBLE-UNTESTED** (N4) |

### BLOCKING

**B1 (statement c).** Prescaling alone does not remove idle_count's activity.
Nearly all of it is in the low bits: bits 0-6 account for 412,800 of the 416,000
register toggles, and the same weighting holds for the carry/next-state logic.

- **Dedicated prescaler.** A free-running divide-by-104 prescaler has the same
  roughly 2 toggles per clock in its own low bits. It only moves the activity
  somewhere else.
- **Reusing the RX bit timer's tick.** The RX timer stops in IDLE, which is
  exactly the stalled-sender case the timeout exists to catch. To make this work,
  the timer would have to free-run while the adapter is in HEAD1/PAYLOAD.

Suggested replacement, to be marked PLAUSIBLE-UNTESTED: "idle_count runs on
every clock during reception and accounts for about 26 % of board transitions.
One option is to count only while the receiver is idle between bytes, because a
byte in progress always finishes. In this workload that is about 52 of 1,040
clocks per byte, which would remove roughly 95 % of its increments. Another
option is to reuse the RX bit-timer tick, made to free-run in HEAD1/PAYLOAD. Any
redesign changes the timeout logic and must pass the existing UART
timeout/error regressions."

### NON-BLOCKING

**N1 (statement a).** "At most the input register plus downstream effects" is
not a bound. Recoding the inputs requires retraining, and the retrained network
can change any core activity. There are three further problems:

- **Wrong provenance for ~3 %.** The 3 % (13,097/384,982 = 3.40 %) comes from
  4.13: a different model, zero-delay, standalone core, 270 validation images.
  In this board capture, the core's input register `core.l0` has 442 of 32,580
  core timed transitions (1.36 %).
- **Correct board-level bound.** In this workload, the board transitions that
  input recoding could change are:
  - the core: 0.68 %
  - the image path (`receiver.shift`, `rx_data`, `image`, `core_image`):
    2,360 transitions, 0.05 %

  Together that is about **0.73 %**, *unless the input width changes*.
- **Unit-distance property.** The current code is a 3-level thermometer code
  (`dlgn/data.py`, thresholds 0.25/0.5/0.75), so adjacent levels already differ
  by one bit. Gray coding's classic benefit already holds. A 2-bit Gray (or
  binary) code would help mainly by having **fewer bits**: 128 instead of 192,
  so the request drops from 24 to 16 payload bytes. That shortens UART time per
  prediction by about 8/39 bytes (≈ 20 %), with matching reductions in clock and
  counter activity per prediction. That interface effect, untested, is much
  larger than any core effect. It comes from the code's width, not from the Gray
  property.

**N2 (script, claim 1).** The script misses RX timer bits 4-6 (see §2). With
them, the register share is 21.66 % instead of 21.16 %. The carry-entry LCs stay
in `unclassified` and have to be added by hand to reach "two-thirds". None of
the rounded statements change. Suggested fix: assign flip-flops by clock-enable
or carry-chain membership, or keep an explicit, documented list (c3998, c3999,
c4006, c24, c6, c26) in the script and the JSON, so the summary's numbers can be
read directly from the output.

**N3 (statement d).** Clock edges per prediction equal f × T_pred. T_pred is set
by 390 bit periods (39 bytes × 10 bits), so the clock part is exact arithmetic.
Counter toggles per prediction are roughly 2 × clocks of active counting, so they
should scale about linearly with clocks per bit. This has not been tested. The
statement should also note:

- **Constraints.** The RTL requires CLKS_PER_BIT ≥ 8. RX_TIMEOUT_CYCLES would
  need rescaling.
- **Clock sources.** The iCE40 PLL's minimum output is about 16 MHz (from the
  Lattice datasheet as I recall it; not checked in this review), so a clock below
  12 MHz cannot come from the PLL. The alternatives are a fabric divider, which
  is itself a toggling counter, or HFOSC, whose ±10 % accuracy is poor for UART.
- **What does not change.** Core transitions per prediction stay the same, and so
  does static energy per prediction (static power × fixed time).

**N4 (statement e).** As a fanout proxy, the clock global net drives **911**
sinks, while each counter bit-0 net drives 4 and each carry-entry COUT drives 1
on dedicated carry wiring. No capacitance or power estimate exists, so "far
exceeds" is plausible but not measured. Count shares are not power shares in
either direction. The 521,665 carry-entry transitions are probably cheap per
transition.

### NOTES

- **N5.** The script does not record its own hash or git commit, does not assert
  that the unknown columns are zero (they are), and has no regression test. It
  would be cheap to add tests that pin the six hand-verified nets.
- **N6. Clock counting convention.** The 27.2 % counts one clock twice: the pad
  net `clk$SB_IO_IN` (1 sink, to the global buffer) and the global net (911
  sinks). Counting it once gives a clock share of 15.7 %, and the counters become
  78.8 % of 4,137,739 transitions. Excluding the clock entirely, the counters are
  93.6 % of the 3,486,379 non-clock transitions. State the convention.
- **N7. Interface, not network.** The counters, clock and image path are
  interface or workload properties. Recoding them changes nothing in the learned
  network. Per the project rules, keep interface-activity savings separate from
  DLGN switching claims.
- **N8. Gray-coding counters (statement b).** On iCE40, Gray increment/decrement
  does not map onto the carry chain. It needs Gray↔binary conversion or XOR
  logic, which may raise next-state LUT activity and glitches. The net effect
  could be negative. The ≈ 2.0 → ≈ 1.0 register toggles per increment, at most
  about 10.6 % of board transitions, is an upper bound for the register part
  only. It ignores reload transitions on wrap/reset, which are small.

## 5. Limitations of the evidence

- 8 requests (first 8 images of the saved test order). The model is the
  historical exploratory `digits_w1000`, not the matched 4.x control.
- One placement and route: the bit-identical reroute of the archived head-only
  UART build. One nextpnr delay corner, no timing checks.
- Icarus applies delays inertially: pulses shorter than a path delay are
  swallowed. Glitch counts in the next-state logic depend on the model, and they
  are not a strict bound.
- Ideal back-to-back host with a 208-clock gap between requests. Real USB/OS
  gaps would change the clock and idle_count shares.
- Transition counts have no capacitance weighting. No power or energy evidence
  exists. Statements (b)-(d) describe untested design changes.
