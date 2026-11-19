# H02 Project Context

Background for anyone (or any AI assistant) working in this repo.
Last updated: Nov 18, 2026.

## Who and why

- **Anoop**, M.S. ECE at UC Santa Cruz (started Fall 2025, graduating June 2027).
- 4 years of industry experience as a Test and Validation Engineer, so verification is a strength.
- Goal: low-power AI inference hardware. This class project is meant to become his
  **master's project**, lead to a paper, and get him into the professor's neuromorphic research group.
  He pitched this to the professor on Oct 22, 2026.

## The class project (ECE 210, Brain-Inspired Machine Learning)

Professor's project H02: train a small differentiable logic-gate network, discretize
the gates, and map the result into an FPGA workflow.

- **Baseline:** compare three versions; hard software and RTL must agree:
  1. soft training model (each gate is a softmax mix of 16 rules)
  2. hard-gate software model (each gate locked to its top rule)
  3. RTL simulation (must match the hard model **bit for bit**)
- **Measure:** accuracy after discretization, LUTs, FFs, latency, Fmax.
- **Professor's stretch options:** deploy to a board, or compare against a small quantized NN.
- **Scope advice:** toy task or reduced dataset first, confirm the synthesis toolchain early,
  simulation as fallback.
- **Base paper:** Petersen et al., "Deep Differentiable Logic Gate Networks", NeurIPS 2022
  (difflogic library). Paper's MNIST "small" model: 6 layers x 8,000 gates, tau = 10,
  97.69% accuracy, discretization gap < 0.1%.
- **Dates:** proposal presentation **Oct 30, 2026**; final submission and presentation **Dec 4, 2026**.

## The extension (Anoop's own idea)

**Power-aware learned logic.** Dynamic power comes from gates switching. Estimate and
reduce that switching during training:

- For gate g, let p_g = probability it outputs 1 across the input distribution
  (mean of its soft output over a batch). If consecutive inputs are independent,
  expected toggle rate is **alpha_g = 2 p_g (1 - p_g)**.
- Add `lambda * mean(alpha_g)` to the loss, sweep lambda, and plot
  **accuracy vs. measured energy**.
- Measure real activity from simulation (VCD/SAIF) and feed it to the FPGA power estimator.
  Report dynamic and static (leakage) power separately.
- Important: p must be the **batch mean**, not per-sample. Per-sample 2a(1-a) only pushes
  outputs toward 0/1 (discreteness), it does not measure switching. That variant is kept
  as an ablation (`--act-mode sample`).
- Relevant prior work includes [Silicon Aware Neural Networks](https://arxiv.org/abs/2604.19334)
  (hardware-area-aware DLGN training) and [DiffPower](https://arxiv.org/abs/2608.03778)
  (differentiable switching-power analysis/optimization). Broad novelty for
  differentiable power optimization is not established. A narrower candidate is
  DLGN gate-rule learning evaluated against mapped/measured FPGA energy.
- Possible venues: ISLPED, FPL, FCCM, DATE, ICCAD.

**Master's-level follow-ons:** glitch-aware training (real gates toggle more than the
zero-delay estimate), timing-aware training, event-driven (event-camera) inputs as the
neuromorphic link, and an open-source ASIC flow using the same Verilog.

**One-sentence pitch:** measure how much energy a logic-gate network burns when its gates
switch, and train the network itself to switch less while staying accurate.

## Hardware and tools

- **Owns:** iCEBreaker (Lattice iCE40 UltraPlus 5K, 5,280 LUT4s). Use for the toy demo and
  to confirm the open-source flow (Yosys + nextpnr). Too small for the paper-size MNIST model.
- **Main numbers (LUTs, FFs, Fmax, SAIF power):** Vivado targeting an AMD/Xilinx part
  (e.g. Artix-7). No board needed for synthesis, timing, or power estimation.
- **Open:** which board and Vivado version the class uses; whether the professor accepts the
  power-aware loss as the stretch goal instead of the quantized-NN comparison.
- **Open:** patent/disclosure timing before presenting the power idea publicly on Dec 4.
  Keep the repo private until that is decided.

## Week-by-week plan

1. Oct 20-26: confirm board/tools; train small model; synthesize a toy design.
2. Oct 27-30: hard-gate evaluator; soft vs. hard accuracy gap; **proposal slides**.
3. Nov 2-8: Verilog export (gates, popcount, argmax); bit-exact testbench.
4. Nov 9-15: synthesis/implementation; LUTs, FFs, Fmax, latency; pipelined vs. combinational.
5. Nov 16-22: SAIF-based power; 2-3 model sizes on full MNIST.
6. Nov 23-29: stretch goal (power-aware training); Thanksgiving slack.
7. Nov 30-Dec 4: report, slides, demo, clean repo.

## Status (updated Nov 18)

- Toy training completed: `runs/digits_w1000`, digits dataset, 4 layers x 1,000
  gates, 60 epochs, seed 0, no activity penalty. Soft accuracy 93.78%; hard and
  NumPy reference accuracy 93.56%; discretization gap 0.22 percentage points.
  PyTorch hard-model scores match the NumPy reference.
- Removed a stray backtick at the start of `tests/test_gates.py` that prevented
  test collection. Before step 4.10 edits, a fresh Nov 18 full suite passed
  **255 tests in 17.06 seconds**, no skips. After step 4.10's 23 new selection
  cases and 7 independent cases, the full suite passed **285 in 19.18 seconds**,
  no skips. Earlier per-step totals below remain dated historical records.
- Re-ran the trained model's combinational simulation and exported/simulated its
  pipelined version. Both pass **450/450 vectors**, comparing every integer
  class score and the predicted class with the NumPy reference. This covers the
  supplied test inputs; it is not formal equivalence over every possible input.
- Synthesized both versions with Yosys 0.63, targeting iCE40:

  | Version | LUT4 | Flip-flops | Carry cells | Register stages |
  |---|---:|---:|---:|---:|
  | `rtl_comb` (input/output registers) | 2,929 | 268 | 123 | 2 |
  | `rtl_pipe` (also registers each logic layer) | 4,528 | 3,523 | 123 | 6 |

- Both designs accept one input per clock. Pipelining adds storage and prevents
  some optimization across layer boundaries; clock-speed improvement is still
  unmeasured. The testbench's nominal 100 MHz clock is not an Fmax measurement.
- Saved logs: `runs/digits_w1000/rtl_{comb,pipe}/sim.log`,
  `synth_ice40.log`, and `synth_ice40_stat.txt`; latency in `params.json`.
  Generated runs are gitignored; the table above preserves the result in source.
- **Timing tool flow established (checklist 2.5):** target iCE40UP5K/SG48 with
  a 12 MHz clock; Yosys 0.63, Homebrew nextpnr-ice40 0.11.1_2, and IceStorm 1.1_1.
  `bash synth/check_ice40_flow.sh` passed synthesis, placement/routing, timing,
  and bitstream generation on a small 24-bit counter with fixed clock/LED pins.
  Post-route estimated Fmax was 79.74 MHz (12 MHz target met), with 28 packed
  logic cells. **This is the counter's timing, not the DLGN's.** Reports and
  bitstream are in `runs/toolchain_smoke/`; no hardware was programmed.
- At the end of 2.5, DLGN placement/routing and timing were still pending.
  See the 2.8 results below for the subsequent routed candidate. Physical board
  deployment, power estimation and meaningful activity-penalty experiments
  remain pending. Vivado is not configured.
- **UART interface complete (checklist 2.6):** `scripts/export_uart.py` wraps the
  core with an 8N1 UART interface, nominally 115200 baud on a 12 MHz clock.
  `board_top` exposes clock, active-low button reset, serial RX and serial TX.
  Each request has a 2-byte header and 24 encoded image bytes; each response has
  a 2-byte header, predicted class, and all ten integer scores. The FPGA's USB
  serial bridge handles the physical connection; no USB logic is added to RTL.
- Both UART versions pass **450/450 images** against NumPy, exercising the
  actual serial pins with an accelerated 8-clocks/bit simulation divider.
  Focused regressions use the hardware's 104-clocks/bit divider and check baud
  mismatch, header parsing, timeout/error recovery, reset, padding, and ties.
  Simulation logs are in `runs/digits_w1000/uart_{comb,pipe}/sim.log`.
- Both complete board tops synthesize with Yosys 0.63:

  | UART version | LUT4 | Flip-flops | Carry cells |
  |---|---:|---:|---:|
  | `uart_comb` | 3,440 | 648 | 167 |
  | `uart_pipe` | 5,059 | 3,903 | 167 |

  These are pre-packing synthesis counts, not proof of physical fit. The
  pipelined version leaves little LUT headroom; placement/routing must establish
  whether it fits. Reports: `synth_uart.log` and `synth_uart_stat.txt` per export.
  See `docs/UART_INTERFACE.md` for protocol, commands, pins and limitations.
- **Constraints complete (checklist 2.7):** added `synth/icebreaker_uart.sdc`
  for a 12 MHz / 83.333 ns clock and `synth/implement_uart_ice40.sh` to apply
  the PCF and SDC. The mapped-netlist checker verifies all four pins, the single
  register clock, the RX synchronizer chain and the reset-release chain. No
  timing exceptions are applied; upstream nextpnr's generic false-path command
  is a no-op. This is structural review, not metastability/physical CDC signoff.
- Both designs accepted the constraints and packed. **Original UART: 3,795 of
  5,280 logic cells. Pipelined UART: 6,236 of 5,280 (over capacity).** The wrapper
  script now saves a capacity report and exits 3 on the latter instead of
  reporting overall success. Cell packing, not separate LUT/FF counts,
  establishes this resource limitation. Reports are in each UART run directory:
  `constraint_audit.json`, `pack_uart.log`, and `pack_uart_report.json`.
- Learning documentation is backfilled for all **21 completed checklist items**,
  beginning with 1.1, in [docs/steps/README.md](steps/README.md). Each has a
  numbered Markdown note with purpose, method, example, evidence, code links,
  limitations and references to older notes. Local documentation links were
  checked; the older Excel tracker remains a separate snapshot.
- **Step 2.8 implementation/review (Nov 14):** the original UART design routed
  but failed the unchanged 12 MHz clock target (7.26 MHz estimate). Fixed with
  an optional score-register bank and balanced argmax tree (`--head-pipeline`),
  giving 3 register stages (2 elapsed clocks to output availability, 3 to
  downstream capture). Also made UART image commit
  atomic to prevent partial-image switching from confounding inference activity.
- The corrected candidate (`uart_comb_head`) uses **3,449 LUT4, 911 flip-flops,
  167 carry cells; 4,160/5,280 packed logic cells**. It routed successfully and
  met 12 MHz with **19.3858566 MHz post-route estimated maximum**. This is a
  tool estimate, not a measured board frequency. The current full-layer plus
  head-pipelined/atomic candidate (`uart_pipe_head`, 7 stages) needs **6,575/5,280
  cells**, so it is rejected before routing. Do not silently label both routed.
- Corrected UART RTL matches all 450 saved images bit for bit. Functional
  simulation of synthesized iCE40 primitives passes 12 images using the real
  UART divider/timeout. That simulation is not routed-delay/glitch simulation.
  The independent verifier reran placement/routing, checked all final hashes,
  added 16 exhaustive cases (16,384 synthetic input evaluations), ran a separate
  3-image mapped check, and found no remaining blocking defect in this scope.
- Fresh attempt folders, status files, synthesis fingerprints, archived-input
  validation and timing/capacity/BEL/log checks prevent stale output from being
  called a successful new run. Final root evidence:
  `runs/digits_w1000/uart_comb_head/implementation.UVAx2g/`; independent rerun:
  `implementation.ogVBqL/`. Tracked summary: [step-2.8-results.json](results/step-2.8-results.json).
  Walkthrough: [step 2.8](steps/2.8-place-and-route.md); review:
  [independent verification](reviews/step-2.8-independent-review.md).
- **Research correction:** future training monitors validation, not test,
  uses fixed partition seed separately from model seed, and saves split indices
  and checkpoints. Digits now has 1,077 train / 270 validation / 450 test.
  Existing 93.56% baseline used 1,347 training examples and exposed test metrics;
  preserve it as exploratory. Retrain both control and penalty models with the
  same corrected protocol; the already inspected digits test is not pristine.
  One-epoch smoke runs verify code paths only, not energy/accuracy improvements.
- **Research verdict:** proceed conditionally. Freeze target, head architecture,
  clock, input order and valid/workload pattern; repeat seeds and select using
  validation. Logical switching depends on sequence order and is not energy.
  Use a supported device-specific power flow or measured rail power. Vivado
  analysis on an AMD target would be a separate device experiment, not UP5K
  power evidence. Full literature differentiation and energy benefit are unproven.
- **Step 2.9 timing audit (Nov 14):** `scripts/report_timing.py` verifies the
  saved attempt status, nine archived file hashes, parameter provenance,
  target/capacity/completion evidence and final clock result. It reads archives
  without invoking FPGA tools or rewriting their validation records. Primary
  and independent archives agree: 19.3858566 MHz estimated Fmax; 51.584 ns
  same-clock input-register-to-score-register path, including 33.865 ns routing,
  15.505 ns combinational logic, 1.390 ns clock-to-output and 0.824 ns setup.
  The required clock remains 12 MHz; this is a revalidation of saved timing,
  not a new implementation run or physical clock measurement. Older archives
  without an executable fingerprint are explicitly labeled as missing it.
  See [step 2.9](steps/2.9-read-and-verify-clock-timing.md) and
  [timing summary](results/step-2.9-timing.json). The independent verifier added
  18 report fault/compatibility cases; the full suite passed 63 tests in 10.62 s.
  Review: [step 2.9](reviews/step-2.9-independent-review.md).
  Step 2.9 remains partial across
  architectures because the full-layer candidate cannot fit and has no Fmax.
- **Step 2.10 performance report (Nov 15):** added
  `scripts/report_performance.py` and `rtl/tb_performance.sv`; regenerated exact
  RTL from the matched model and fresh NumPy score/class vectors. Each current
  architecture passes 32 streaming core vectors and 3 full UART transactions
  at the hardware divider of 104. The feasible head candidate has 3 register
  stages, output availability after 2 elapsed clocks and downstream capture
  after 3; initiation interval is 1. At the qualified 12 MHz these are
  cycle-equivalent 166.67 ns / 250 ns, not measured physical propagation times.
  Its calculated standalone interface capacity is 12 million images/s;
  the existing UART board interface cannot supply an image each clock.
- Feasible UART first-request-start to final-reply-stop completion is
  40,528.5 clocks (cycle-equivalent 3.377375 ms); the benchmark's immediate
  ideal-host request-start interval is 40,529 clocks, about 296.0843 images/s.
  USB/OS delays and physical board operation are not measured. The sum of all
  directional byte times is 40,560 clocks, but it is not a wall-time lower
  bound: the last request stop bit can overlap the reply on the other wire.
- The full-layer candidate simulates 6 clocks to port / 7 to downstream
  capture and 40,532.5-clock UART transactions. Its timing-qualified
  nanosecond values, Fmax and throughput remain unavailable because it cannot
  fit. Step 2.10 is partial as a two-architecture hardware comparison.
  Independent tests cover all four register configurations, input bubbles,
  UART boundaries, the shipped benchmark and matched-model/workload guards.
  The initial benchmark's delta-cycle premature-completion failure was fixed
  in the testbench only; its failed logs are retained. See
  [step 2.10](steps/2.10-compare-latency-and-throughput.md),
  [results](results/step-2.10-performance.json) and
  [independent review](reviews/step-2.10-independent-review.md).
- **Step 3.2 recording check (Nov 16, independently verified):** added
  `scripts/check_waveform_recording.py`. Fresh Icarus exports of the first eight
  historical images pass exact score/class checks with recording on and off
  for both original and head-only cores. Off produces no VCD; on records the
  input/layer/output buses and clock/reset/valid with advancing timestamps.
  Source/vector hashes match across recording modes. Primary evidence:
  `runs/digits_w1000/waveform-check.njxy5prx/result.json`;
  [walkthrough](steps/3.2-verify-waveform-recording.md) and
  [tracked summary](results/step-3.2-waveform-recording.json).
  Independent rerun: `waveform-check.am2eksx1/result.json` under the same model
  directory. The verifier checked all source/tool/artifact hashes and independently
  decoded the saved vectors against NumPy. Four simulator cases cover all
  layer/head register combinations; ten inspector cases cover valid aliases,
  unknown startup values and recording faults. All 14 pass with no skips.
  [Independent review](reviews/step-3.2-independent-review.md).
  This is a short nominal-100-MHz functional recording check, not a full
  baseline waveform, qualified 12-MHz workload or activity/energy result.
- **Waveform viewing (Nov 16):** Surfer 0.6.0 was already installed. Opened
  the head-only eight-image VCD and visually verified clock/reset/valid,
  input/layer buses, class and scores. Saved local view:
  `runs/waveform-viewer/head-core-view.ron`; reopen with
  `surfer --state-file runs/waveform-viewer/head-core-view.ron`.
  The local `Surfer.app` launcher wraps an unchanged copy of the Homebrew
  executable because desktop control could not target the bare CLI executable.
  No additional viewer package was required. GTKWave's separate desktop launch
  timed out with cause unestablished; Surfer is the verified viewer here.
- **VS Code waveform viewing (Nov 16):** installed the Marketplace extension
  `lramseyer.vaporview` 1.6.1 and opened the same eight-image head-only VCD in
  the project window. Visually verified all twelve selected clock/control,
  input/layer and output signals. Open `.vcd` files in VS Code and double-click
  signals in the VaporView Netlist to display them. No rerun or RTL change was
  needed; Surfer remains an available standalone option.
- **Step 3.3 full baseline capture (Nov 16, independently verified):** added
  `scripts/capture_baseline_waveform.py` and `rtl/tb_activity_capture.sv`.
  All 450 saved inputs, unchanged order, pass every integer score/class check
  using the historical unpenalized model and the feasible head-only core.
  Regenerated core matches the existing export and archived passing
  implementation. Standalone streaming II=1, not UART; three reset cycles,
  falling-edge input drive, post-update output checks and held-input drain.
  VCD includes all DUT signals plus transaction indices/counters and completion.
  Nominal clock is 12 MHz; explicit 1 ps quantization gives an 83,334 ps period
  (11,999,904.000768 Hz simulated). Archived constraints remain unchanged.
  Primary raw report: `runs/digits_w1000/baseline-waveform.xs90rtvt/result.json`;
  VCD is 6,476,465 bytes, ending at 38,083,639 ps. Model/input copies, source/
  executable/artifact hashes, command logs and every capture/check timestamp
  are preserved. See [walkthrough](steps/3.3-capture-the-baseline-waveform.md)
  and [tracked summary](results/step-3.3-baseline-waveform.json).
  Independent fresh capture: `baseline-waveform.q2umneq1/` under the same model
  run. Separate decoding checks all 450 recorded inputs, scores/classes and
  markers in both traces, with exact reset/drain boundaries and 457 rising
  edges at the declared period. Each report's 13 source, 16 artifact and two
  executable hashes passed. Ten independent capture/ledger regressions pass;
  full suite: 95 passed in 10.83 s, no skips. See
  [independent review](reviews/step-3.3-independent-review.md).
  Raw trace includes reset/fill/drain; activity window approval, transition
  totals, alias/unknown accounting and Python/RTL activity agreement remain
  steps 3.4–3.7. This is not mapped-delay, physical power or energy evidence.
- **Step 3.4 activity counter (Nov 16, independently verified):** added
  `dlgn/vcd_activity.py` and `scripts/analyze_waveform.py`. The standard-library
  streaming parser counts bit changes once per VCD identifier, retains aliases,
  excludes first observations from toggles and separates known 0/1 transitions
  from changes touching X/Z. Repeated values are ignored as transitions;
  same-timestamp records would be counted, but Icarus writes each identifier at
  most once per timestamp, so real-capture counts are settled per-timestamp.
  Optional (start,end] mechanics carry state; useful-work selection remains 3.5.
  Unsupported/malformed encodings fail rather than silently produce partial counts.
  Fresh read-only analysis of the archived primary capture:
  `baseline-waveform.xs90rtvt/activity-analysis.zemyttyn/result.json` under the
  historical run. Whole-file diagnostic: 1,036 IDs, 1,843,155 known bit flips
  (921,584 rises, 921,571 falls), 10,897 unknown-involving changes. These include
  clock/control/testbench markers, separate logical copies, reset/fill/drain;
  they are not the validated useful-work network total or a power/energy result.
  The actual trace has no shared-ID aliases; synthetic tests cover that case.
  A separate string-per-bit oracle agrees for every ID on both saved captures;
  fresh independent analyses and audit scripts preserve provenance. Thirty-five
  independent cases cover four-state values, aliases, ranges/timescales,
  same-timestamp records, window mechanics and malformed/tampered inputs.
  Initial two test metadata assumptions (range-free names/numeric timescale)
  were corrected to the explicit report schema; counting semantics did not change.
  Full suite: 130 passed in 10.16 s, no skips. See
  [walkthrough](steps/3.4-count-waveform-transitions.md),
  [summary](results/step-3.4-waveform-activity.json) and
  [independent review](reviews/step-3.4-independent-review.md).
- **Step 3.5 measurement windows (Nov 16, independently verified):** added
  `scripts/report_activity_windows.py`. Each of 14 observation points has 450
  known settled image states and 449 adjacent-image intervals. Windows use
  (first settled state, last settled state] with carried baseline state, shifted
  to each register/combination's availability; no single crop can remove fill
  at all pipeline stages while retaining every image. Current head-only bounds
  in ps: input port (250003,37666969], l0/layers (291670,37708636], head bank/
  winner (375004,37791970], registered scores/class (458338,37875304]. All span
  37,416,966 ps = 449 rounded simulation periods. These are not a shared
  device-energy interval or the finite-burst runtime for 450 predictions.
  Full clock/reset/valid and every raw input-port change are checked, along
  with markers, references, known endpoints and held-input drain. An independent
  verifier found that endpoint-only input checks accepted hidden between-sample
  and drain pulses. The validator now requires the exact normalized falling-edge
  input-change schedule. Both originally accepted malformed captures were
  preserved and independently rechecked to confirm rejection after the fix.
  Final primary evidence under the historical run:
  `baseline-waveform.xs90rtvt/activity-windows.lf7s8aqq/result.json`;
  independent reports: `activity-windows.p4p5y9h0/` under the primary capture
  and `activity-windows.kuy7li2p/` under the independent capture. A separate
  endpoint/provenance audit agrees on all windows; 22 independent tests cover
  all four register configurations, repeated inputs and semantic/hash faults.
  Full suite: 152 passed in 11.78 s, no skips. See
  [walkthrough](steps/3.5-define-activity-windows.md),
  [summary](results/step-3.5-activity-windows.json) and
  [review](reviews/step-3.5-independent-review.md).
  No transition total or logical-layer/NumPy activity comparison is claimed
  here; known sampled endpoints do not erase intermediate recorded events.
- **Step 3.6 categories (Nov 16, independently verified):** added
  `scripts/report_activity_categories.py`. Exact exporter RTL/parameter and
  capture/window checks precede role assignment. Whole-trace categories
  partition all 1,036 IDs and reconcile every counter field; duplicate layer
  views, registers, output logic, clock/control and simulation bookkeeping
  remain explicit. Roles follow the circuit, not the VCD `reg` label;
  `sc_flat` observes the head score bank but is not another register bank.
  Unpacked score arrays are not separately dumped, so this is not a complete
  physical storage inventory or mapped-node breakdown.
  Four canonical layer buses `l1_c`–`l4_c` have 126,546 / 144,016 / 167,436 /
  190,171 settled changes: **628,169 / 1,796,000 = 0.34976002 changes per
  gate per image pair**, with 449 pairs. Four forwarding views are excluded
  from that metric. Recorded layer events agree with settled counts in these
  aligned windows (expected by construction: Icarus records one value per
  identifier per timestamp); this is not physical glitch evidence. Whole-trace category
  sum remains 1,843,155 known flips, including startup and redundant views.
  Primary evidence: `baseline-waveform.xs90rtvt/activity-categories.w0799sk1/`;
  independent reports: `.xs90rtvt/activity-categories.y98xlian/` and
  `.q2umneq1/activity-categories.z_xyxdti/` under `runs/digits_w1000/`.
  Separate raw/endpoint oracles agree on all three reports; all capture/source/
  analysis hashes pass. Twenty independent tests cover four architectures,
  aliases/copies, raw versus settled known/unknown pulses and provenance faults.
  Full suite: **172 passed in 12.25 seconds, no skips**; no blocking finding.
  See [walkthrough](steps/3.6-separate-activity-categories.md),
  [summary](results/step-3.6-activity-categories.json) and
  [review](reviews/step-3.6-independent-review.md).
  This is a logical switching proxy, not energy, regularizer benefit or novelty.
- **Step 3.7 NumPy/RTL activity (Nov 16, independently verified):** added
  `scripts/compare_activity_numpy.py`. It binds the saved NumPy inputs/order,
  model and fresh reference scores/classes to the capture, revalidates stage
  windows, and compares every settled state and adjacent-image XOR mask,
  followed by totals/rises/falls and per-gate counts. All **14 observations
  match across 450 images**, including six tied-score images with lowest-index
  winners. Zero sampled-state, transition-mask or per-gate discrepancies.
  Canonical layers match NumPy exactly: 126,546 / 144,016 / 167,436 / 190,171
  changes; total **628,169 / 1,796,000 = 0.34976002227171493**, with 314,079
  rises and 314,090 falls. Fresh original `hard.toggle_rate` agrees. Raw
  aligned observation counts also agree here; whole-file diagnostic counts
  include other categories/startup and are a different measurement.
  Primary read-only analysis under the historical run:
  `baseline-waveform.xs90rtvt/activity-numpy.e4k0xtre/result.json`;
  independent reports: `.xs90rtvt/activity-numpy.vsauy9f4/` and
  `.q2umneq1/activity-numpy.e5oitt9n/` under `runs/digits_w1000/`.
  Separate scalar-gate, line-decoded VCD and raw-event oracles audit all three
  reports, full archived settled sequences and all provenance hashes.
  Twenty-two independent tests cover four architectures, bit order, incorrect
  states despite matching toggle totals, copies/registers, repeated inputs,
  explicit ties, known/X pulses and reference/provenance faults. An initial
  test incorrectly assumed repeated inputs guarantee score ties; a separate
  deliberate tied-score fixture now verifies that property. Original failing
  evidence and exact reproduction are preserved, with the correction rechecked.
  Full suite: **194 passed in 13.83 seconds, no skips**; no production blocker.
  See [walkthrough](steps/3.7-cross-check-numpy-and-rtl-activity.md),
  [summary](results/step-3.7-numpy-rtl-activity.json) and
  [review](reviews/step-3.7-independent-review.md).
  This validates a matched logical proxy, not mapped activity, physical
  glitches, power/energy benefit, regularizer effectiveness or novelty.
- **Step 3.8 mapped activity (Nov 16, independently verified):**
  code-review fixes applied: per-timestamp wording (Icarus records one value
  per identifier per timestamp; measured max 1 in mapped trace), source hashes
  taken before copying and rechecked at end, `yosys-config`/`vvp` taken from the
  same install as `yosys`/`iverilog`, start-window and port-width validation,
  clock/control/data input categories, 0/1 check on baseline inputs. Fresh
  capture `runs/digits_w1000/mapped-activity.57fn0ze0/` passes 450/450 and its
  reanalysis; 2,912 LUT4 / 339 FF / 123 carry, 3,569 net bits, 667,463 known
  whole-trace flips (LUT 569,566, FF 51,053, carry 23,856, data input 22,071,
  clock 914, control 3), 0 unknown. Full suite: 239 passed in 13.81 s, no skips.
  Deferred: parser/validator consolidation and repeated VCD passes.
- **Step 3.9 glitch estimate (Nov 16, independently verified):** added
  `scripts/capture_timed_activity.py`. Re-routed the archived head-only UART
  board with `--sdf` (bit-identical bitstream, 19.39 MHz), renamed cells so
  Icarus parses the SDF, and simulated 8 images at 12 MHz with the real UART
  divider, timed (`-gspecify -ginterconnect -DTIMING`) and zero delay. All
  replies exact; per-net settled-change counts identical. Core: 32,580 timed transitions vs
  12,178 settled changes, **1.68 extra per settled change**; interface 0.70.
  Icarus filters pulses narrower than a path delay (inertial); one delay
  corner; not energy. Evidence: `runs/step3.9-glitch/timed-activity.0hvnej44/`.
- **Step 3.10 metrics (Nov 16):** `scripts/report_switching_metrics.py`.
  Surrogate 2p(1−p) 0.3466, random-order expectation 0.3473, saved order
  0.3498 per gate pair (within 1% per layer); saved order acts random
  (difference < 1 permutation std). Layers 0.28→0.42; 499 constant gates.
  The surrogate models settled changes only; routed-core glitches add ~1.7
  transitions per settled change on 8 images.
- **Step 4.10 preparation (Nov 18, independently verified):**
  `scripts/train.py --defer-test` performs no test inference or test export,
  saves fixed-order validation inputs/labels, exact NumPy scores/classes and
  changes/opportunities, and archives configuration, split identities, final
  checkpoint, source/package provenance and status. A frozen policy is copied
  before training. Existing output folders are rejected. The compatibility
  mode without the flag still evaluates test and cannot enter the selector.
  The existing dataset loader still returns test arrays; deferral concerns
  inference, metrics and exports, not an unloaded test dataset.
  `scripts/select_validation_models.py` recomputes validation quantities and
  checks matched data, architecture, training budget, model seed, source and
  versions. It minimizes settled switching within a working one-percentage-
  point accuracy budget relative to the control, with the control selectable.
  This tolerance is not a professor requirement; repeated-seed aggregation is
  not implemented. `scripts/evaluate_selected_model.py` rechecks selection and
  evaluates the selected checkpoint later without retraining, in a new folder.
  Real 1-epoch mechanism evidence: `runs/step4.10-preparation.20uuxoj6/`;
  control selected because the penalty lost 4/270 validation examples
  (1.48148 percentage points), beyond the frozen budget. These undertrained
  smoke runs are not step 4.3 results or evidence of useful optimization.
  See [walkthrough](steps/4.10-prepare-validation-only-selection.md),
  [summary](results/step-4.10-validation-selection.json) and final independent
  [review](reviews/step-4.10-independent-review.md).
- **Professor direction reported Nov 18:** Anoop says the professor encouraged
  pushing the work toward a conference paper. No new venue, deadline, required
  dataset or power-evidence threshold was specified in that update.
- **Step 4.3 initial pair (Nov 18, independently verified):**
  Fresh lambda-zero control and lambda-0.1 batch-penalty model each completed
  60 CPU epochs with the same 4×1,000 architecture, tau 10, Adam/0.01,
  batch size 100, model/split seed 0, 1,077 train / 270 validation, unchanged
  validation order and one-thread environment. All test evaluation is deferred.
  The plan, policy and eight source files were archived before training under
  `runs/step4.3-pair.ixlscii4/`; historical baseline hashes remain unchanged.
  Hard validation: control **249/270 = 92.22%**, lambda 0.1 **245/270 = 90.74%**.
  Settled learned-gate changes: **373,910 vs 346,963 / 1,076,000** opportunities,
  rates **0.347500 vs 0.32245632**. This is **7.2068% fewer logical changes**,
  with a **1.48148-percentage-point accuracy loss**. The loss exceeds the
  frozen 1 pp allowance, so the pair selector retains the control. This is
  a tradeoff result, not an accepted optimization or evidence of energy savings.
  Both PyTorch/NumPy integer scores/classes agree; independent scalar checks
  reproduce all 270 validation images, counts and checkpoint/optimizer progress.
  One lambda and one seed do not establish repeatability, novelty or a
  hardware result. No new full regression was needed: executable code is
  unchanged from the 285-pass step 4.10 suite. See
  [walkthrough](steps/4.3-run-the-initial-penalty-experiment.md),
  [summary](results/step-4.3-initial-penalty-experiment.json) and
  [independent review](reviews/step-4.3-independent-review.md).
- **Step 4.4 sweep (Nov 18, independently verified):**
  Compared lambda **0, 0.001, 0.003, 0.01, 0.03, 0.1, 0.3 and 1** at the
  same seed-0 60-epoch protocol. Six new runs are under
  `runs/step4.4-sweep.zlmbqzyd/`; the verified 4.3 lambda-zero and lambda-0.1
  runs were explicitly reused, not rerun or presented as fresh output. The
  grid was chosen after the known 4.3 results, then fixed before six new runs.
  The original one-percentage-point accuracy allowance was unchanged.
  The selector chooses **lambda 0.3**: **247/270 = 91.4815%** hard validation
  accuracy, **309,698/1,076,000 = 0.28782342** settled changes per gate/pair.
  Against the matched control's 249/270 and 373,910 changes, this is
  **17.1731% fewer logical changes at 0.74074 pp accuracy cost**, satisfying
  the frozen allowance. Lambda 1 lowers changes 42.30% but only gets 236/270
  correct, so it is rejected. Lambda 0.001 slightly increases switching.
  All eight checkpoints are final epoch 60; independent scalar checks match
  every validation score/class and exact count, all Adam steps are 660, and
  source/policy/data/order identities agree. No executable code changed; the
  285-test result remains the prior step 4.10 run, not a new sweep test run.
  All test evaluation is deferred. This is a provisional within-grid choice
  for repeated-seed testing, not a final paper model, hardware result, energy
  improvement or novelty claim. See [walkthrough](steps/4.4-sweep-penalty-strengths.md),
  [summary](results/step-4.4-penalty-strength-sweep.json) and
  [independent review](reviews/step-4.4-independent-review.md).
- **Step 4.5 repeated seeds (Nov 18, independently verified):**
  Fixed lambda 0.3 after discovery seed 0; trained eight new 60-epoch models
  as matched control/penalty pairs for seeds 1–4. Reused the two verified
  seed-0 models explicitly. The prewritten plan, frozen policy and eight-file
  source snapshot are under `runs/step4.5-seeds.vyq2h2nf/`. The same 1,077
  training / 270 validation images and validation order remain fixed; only
  model seed varies connections, initial weights and minibatch shuffle.
  Primary reporting excludes the discovery pair. All four new pairs lower
  settled learned-gate changes, by **16.0357%, 16.7279%, 16.2527%, 17.8436%**.
  Accuracy losses are **1.1111, 2.2222, 0, 2.5926 percentage points** against
  each seed's own control. Only **1/4** meets the frozen one-point allowance.
  The predeclared conservative all-four consistency rule therefore fails.
  Mean per-pair reduction is **16.71498%**, sample SD **0.80604 percentage
  points**; mean accuracy loss **1.48148 pp**, sample SD **1.17121 pp**.
  Pooled-count reduction is separately **16.71602%**. Including discovery
  gives a secondary, selection-informed mean of 16.80661% with 1.33333 pp
  accuracy loss and 2/5 joint passes; it is not the primary repeat assessment.
  No failed-accuracy seed was removed, lambda was not retuned and the budget
  was not relaxed. Lambda 0.3 is not a consistently acceptable default under
  this rule, despite the repeated lower-switching pattern in these runs.
  Independent scalar/checkpoint/RNG audits match all ten models (2,700
  model-image computations, still the same 270 distinct validation images).
  Descriptive sample SD is not a confidence interval or dataset-level claim.
  No test evaluation or new RTL/hardware/power/energy result was produced.
  Training code is unchanged; the 285-test result remains from step 4.10.
  See [walkthrough](steps/4.5-repeat-the-selected-penalty-across-seeds.md),
  [summary](results/step-4.5-repeated-seeds.json) and
  [independent review](reviews/step-4.5-independent-review.md).
- **Research discussion recorded Nov 18:** Anoop questioned whether the
  seed-0 lambda-0.03 result (2.05% fewer logical changes at 0.74 pp accuracy
  loss) would yield enough energy benefit to justify pursuing it. The
  assistant revised its earlier weaker-penalty recommendation: prioritize
  planning a supported power flow and a bounded matched control/lambda-0.3
  hardware-energy pilot to assess whether logical reductions matter in energy.
  This is a discussed recommendation, not a completed or launched experiment.
  No power flow has been selected or energy reduction demonstrated. Full
  discussion: [switching versus energy](discussions/2026-11-18-switching-versus-energy.md).
- **Follow-up discussion recorded Nov 18:** energy cannot be checked now (no
  power tool installed; Radiant/Vivado need x86). Anoop set a working rule:
  under 2% energy saving is not worth pursuing as a power-saving claim; a
  characterization paper (how much logical reduction survives mapping,
  routing, glitches and power) was discussed as a possible MCSoC framing,
  pending professor review. Nine plan deviations/additions are proposed,
  awaiting approval, including validation-vector export, a predeclared 2%
  stop rule on routed core transitions, generalized mapped/timed activity
  tools and place-and-route seed variability. See
  [small saving and pilot plan](discussions/2026-11-18-small-saving-publication-and-pilot-plan.md).
- **Step 4.12 stop rule (Nov 18, independently verified):** Anoop approved
  four added steps (3.11, 4.12–4.14; 65 tasks). Frozen policy
  `docs/experiments/hardware-switching-stop-rule-v3.json` (SHA-256 5d22135a…),
  amended twice before any new-model hardware run after review (v1 cde1fbd,
  v2 f5f8304). 2% threshold on **core** switching (not board share; on the
  UART board the core is ~0.9% of 3.9 board transitions). Probe (seed 1,
  zero-delay mapped): PAUSE iff M1 raw and M2 fanout-weighted R < 2%. Final
  (seeds 1–4, routed SDF, placements 1–3): implementation failure →
  INCONCLUSIVE; STOP if both < 2%; PROCEED needs ≥ 2% beyond 2× placement
  noise. Lambda 0.3 stays an accuracy-failed diagnostic. See
  [walkthrough](steps/4.12-freeze-the-hardware-stop-rule.md) and
  [review](reviews/step-4.12-independent-review.md).
- **Step 4.13 probe (Nov 18, independently verified):** seed-1 control vs
  λ=0.3, 270 validation images, both 270/270 RTL and mapped exact. Logical
  16.0% reduction becomes **3.2% mapped core toggles (M1)** and **3.9%
  fanout-weighted (M2; 2.37% excluding an input-register load difference)**.
  Frozen rule: **CONTINUE**, thin margin. Analysis: penalty saves mostly in
  layers 1–2 (layer 4 only 3.6%); popcount/adder LUTs ≈60% of mapped toggles
  and nearly unchanged; only ~870/4,000 gates survive as nets. Suggests a
  uniform gate penalty mis-targets post-mapping cost (untested idea). Evidence:
  `runs/step4.13-probe.nakln11l/`; [walkthrough](steps/4.13-run-the-screening-probe.md),
  [summary](results/step-4.13-screening-probe.json), [review](reviews/step-4.13-independent-review.md).
- **Step 4.15 layer targeting (Nov 19, independently verified):** per-layer
  penalty weights (L4, L34, M23, RAMP) vs uniform, λ 0.1/0.2/0.3, 28 models.
  Outcome **TARGETING_NOT_SHOWN**: seed-1 T* RAMP 0.3 (2.41% mapped) vs U*
  uniform 0.2 (2.64%); RAMP fails accuracy on seeds 2 and 4. Last-layer-only
  moves switching < 1%; mechanism unestablished (class-vote explanation not
  supported). Within the 1 pp rule, mapped core-toggle reduction ≤ ~3.6% in
  every model; about one fifth of logical savings survive mapping. Paper
  direction leans to characterization; discuss with professor before 4.14.
  See [walkthrough](steps/4.15-test-a-layer-targeted-penalty.md).
- **Next research decision:** assess the proposed energy pilot before more
  weaker-lambda tuning. Do not promote lambda 0.3 as a robust default,
  cherry-pick seed 3 or relabel failed accuracy decisions. Step 4.6's own
  RTL checks and implementation feasibility remain necessary for any new
  model; steps 5.1–5.5 provide the uncompleted power/energy work. Any revised
  accuracy target needs a separate recorded comparison. Keep test evaluation
  deferred while selecting.
  The non-blocking shared-VCD-parser/validator consolidation remains before
  larger hardware-activity batches. This NumPy-only training sweep did not
  use that path or refactor measurement code.
  The full-layer design still needs
  resizing or a larger target for a second hardware performance result.
  Routed neural-network configuration evidence exists, including the bit-identical
  step 3.9 reroute; no physical board has been programmed. A live serial
  host client is still pending. UART throughput must not be reported as the
  core's maximum throughput; power claims must specify the workload.

Reproduce the pipeline comparison (from the repo root):

```bash
.venv/bin/python -m pytest tests -q
.venv/bin/python scripts/export.py runs/digits_w1000 --pipeline
bash sim/run_sim.sh runs/digits_w1000/rtl_comb
bash sim/run_sim.sh runs/digits_w1000/rtl_pipe
bash synth/synth_ice40.sh runs/digits_w1000/rtl_comb
bash synth/synth_ice40.sh runs/digits_w1000/rtl_pipe
```

## Persistent checklist and research priorities (Nov 13)

- Anoop supplied a detailed 57-task status checklist on Nov 13 and requested
  that it be retained as project memory. Full snapshot: [PROJECT_CHECKLIST.md](PROJECT_CHECKLIST.md).
- The checklist covers baseline verification, FPGA performance, switching
  measurement, switching-aware training, power/energy evidence, physical
  deployment, and reproducibility/course deliverables. Preserve the distinction
  between completed work, existing code awaiting validation, and pending work.
- Baseline Python logical switching is 0.34976 changes per gate per image
  transition in the saved test order. Short recording checks and a full
  450-image capture now have independently checked VCDs and raw activity counts;
  useful-work windows, categories and exact settled logical/Python values,
  transition masks and per-gate activity agreement are now verified.
- Batch-mean switching-penalty and per-sample ablation code exist; their
  effectiveness has not been tested. No energy reduction has been demonstrated.
- Implementation setup, interface and constraints are complete through 2.7;
  2.8 has an independently validated routed head-only candidate. The full-layer
  candidate remains oversized, so the two-architecture item is partial.
  Mapped activity, a scoped timing-aware glitch assessment and complementary
  metrics were subsequently completed in steps 3.8–3.10. Energy remains unmeasured.
- Research evaluation must use consistent targets, clocks, workloads and
  settings; validation data for selecting penalty strengths; repeated seeds;
  and separate reporting of switching, estimated power and measured energy.
  Ordinary RTL traces do not establish physical glitch activity.
- Physical deployment and electrical measurements are a separate branch.
  MNIST support exists, but experiments and final artifact archival remain.
- Excel tracker: `outputs/h02-tracker-20261113/H02_Project_Tracker.xlsx`.
  It starts from the supplied snapshot; spreadsheet edits do not automatically
  synchronize back to these Markdown notes. Final course deadline: Dec 4, 2026.
- Updated template-based tracker: `outputs/h02-tracker-20261114/H02_Project_Tracker.xlsx`.
  It captures all 57 checklist tasks as of Nov 14: 21 complete, 9 partial,
  27 pending. Partial tasks use the template's `In Progress` status. Dates,
  priorities and task owners remain unassigned unless supported by the notes;
  the Dec 4 final deadline is retained. The spreadsheet is a separate snapshot.
  After the Nov 15 step 2.10 report, the Markdown checklist has 21 complete,
  10 partial and 26 pending tasks; that older workbook has not been refreshed.

## Professor-feedback continuation (Nov 16)

Recovered prior conversation `01a1e2b2-7d25-7680-95f3-94ff4ccff21d` summarized
Professor Eshraghian's suggestions: multiple switching metrics, Gray coding
where relevant, and a manuscript draft for review before submission. The
conversation discussed MCSoC 2027 with a Nov 30 target; verify current venue
dates separately before submission. This is recovered conversational context,
not a verbatim quote or a newly verified venue deadline.

Anoop approved continuing the existing plan with additions, not restarting 1.1:

- **3.10:** compare training surrogate, measured settled logical changes,
  per-layer results, waveform categories and mapped activity where supported.
  Counts and normalized rates are complementary, not independent energy proof.
- **4.10 before 4.3–4.5:** add validation-only sweep mode (the trainer currently
  evaluates test at the end of each run), validation switching and input-order
  artifacts, explicit selection criteria and provenance. Train a new matched
  lambda=0 control and penalized models; retain the old baseline separately.
- **4.11:** investigate Gray coding separately after baseline measurement.
  Grayscale is already the image format; current bit encoding is thermometer.
  Identify useful signals before recoding. Pixel recoding needs retraining and
  explicit quantization/input-width controls; score/counter changes need exact
  function checks and area/timing/activity accounting. Distinguish interface
  activity savings from changes to the learned network.
- **7.6:** start the manuscript alongside experiments and obtain professor
  review before submission. This task list does not authorize sending messages.

No original task is removed. Proceed 3.2–3.7 with complementary reporting,
then matched training and mapped comparison. Power/energy 5.x and physical
deployment 6.x retain their separate evidence requirements. Four pending tasks
were added to the original 57-item checklist; the older Excel tracker is still
a separate, unrefreshed snapshot.
After step 3.10 the Markdown checklist had 61 tasks: 30 complete, 9 partial and
22 pending. After step 4.10, it had 31 complete, 9 partial and 21 pending. After step 4.3, it had 32 complete, 9 partial and 20 pending. After step 4.4, it had 33 complete, 9 partial and 19 pending. With step 4.5
independently verified on Nov 18, it now has
**61 tasks: 34 complete, 9 partial and 18 pending**. Older Excel trackers and
the downloadable Nov 17 learning guide remain dated snapshots.

## How Anoop wants to work

- Use `engineering:debug` when debugging tests or unexpected behavior. Follow
  reproduce → isolate → diagnose → fix, then verify. Summaries should explain
  expected/actual behavior, reproduction steps, root cause, fix, verification
  and prevention. Preserve uncertainty when a root cause is not established.
- For every step, use an independent verification sub-agent to check the code,
  methodology and results. Assess research correctness and relevance, fix
  blocking findings and have the verifier check the corrections. Keep claims
  bounded by evidence. Persist these rules in the root `AGENTS.md`.
- For every completed checklist step, create or update a simple numbered
  Markdown walkthrough in `docs/steps/`. Cover why, what, how, an example,
  evidence, code links and limitations; link older documents by filename.
  Keep `docs/steps/README.md` and the checklist in sync. Backfill completed work
  from 1.1; distinguish code that exists from validated experimental results.
- He is learning this deeply, not just shipping it. The course also asks students to
  understand any AI-suggested fix, not just paste it.
- **Explain step by step**, one small piece at a time, in plain language with an example.
  For each concept cover: What, How, Where it's used, Why, When it matters.
- **Wait for "yes, understood"** before moving to the next piece. Don't dump everything at once.
- Before running long or heavy commands, say what they will do.
- Learning progress so far: (1) logic gates vs. normal neurons, (2) training with a softmax
  mix of 16 rules then discretizing (worked "digit 5" example), (3) exporting to Verilog.
  (4) bit-exact verification: distinction from recognition accuracy explained and
  understood. **Next piece: FPGA resources and pipelining**, then timing, power,
  and the extension.

## Code conventions (see README for layout)

- Gate IDs follow the paper's Table 1. The truth table bits f(0,0) f(0,1) f(1,0) f(1,1),
  read MSB first, equal the gate ID, so `out = (id >> (3 - (2a + b))) & 1`.
- `dlgn/hard.py` is the golden model. RTL must match its integer class scores and its
  argmax, with **ties going to the lowest class index**.
- Model hand-off format is `runs/<name>/model.json` (connections + gate IDs per layer).
- Generated RTL always registers inputs and outputs, so Fmax is a register-to-register
  tool estimate. `LAT` counts register stages: depth + 2 with `--pipeline`,
  otherwise 2, plus one for `--head-pipeline`. From input capture, port
  availability is after `LAT-1` elapsed clocks; downstream capture is at `LAT`.
