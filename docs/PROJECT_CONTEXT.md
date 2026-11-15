# H02 Project Context

Background for anyone (or any AI assistant) working in this repo.
Last updated: Nov 14, 2026.

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

## Status (updated Nov 14)

- Toy training completed: `runs/digits_w1000`, digits dataset, 4 layers x 1,000
  gates, 60 epochs, seed 0, no activity penalty. Soft accuracy 93.78%; hard and
  NumPy reference accuracy 93.56%; discretization gap 0.22 percentage points.
  PyTorch hard-model scores match the NumPy reference.
- Removed a stray backtick at the start of `tests/test_gates.py` that prevented
  test collection. Latest `.venv/bin/python -m pytest tests -q`: **45 passed**,
  including independent exhaustive head-pipeline and artifact/protocol checks.
- Re-ran the trained model's combinational simulation and exported/simulated its
  pipelined version. Both pass **450/450 vectors**, comparing every integer
  class score and the predicted class with the NumPy reference. This covers the
  supplied test inputs; it is not formal equivalence over every possible input.
- Synthesized both versions with Yosys 0.63, targeting iCE40:

  | Version | LUT4 | Flip-flops | Carry cells | Latency (cycles) |
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
  giving a 3-cycle core valid-interface latency. Also made UART image commit
  atomic to prevent partial-image switching from confounding inference activity.
- The corrected candidate (`uart_comb_head`) uses **3,449 LUT4, 911 flip-flops,
  167 carry cells; 4,160/5,280 packed logic cells**. It routed successfully and
  met 12 MHz with **19.3858566 MHz post-route estimated maximum**. This is a
  tool estimate, not a measured board frequency. The current full-layer plus
  head-pipelined/atomic candidate (`uart_pipe_head`, 7 cycles) needs **6,575/5,280
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
- **Next:** consolidate 2.9–2.10 performance reporting for the feasible candidate,
  then mapped activity. The full-layer design needs resizing or a larger target.
  No neural-network bitstream has been generated or programmed. A live serial
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
  transition in the saved test order. Waveform recording support exists, but
  baseline VCD capture and activity-analysis validation remain pending.
- Batch-mean switching-penalty and per-sample ablation code exist; their
  effectiveness has not been tested. No energy reduction has been demonstrated.
- Implementation setup, interface and constraints are complete through 2.7;
  2.8 has an independently validated routed head-only candidate. The full-layer
  candidate remains oversized, so the two-architecture item is partial.
  Next activity work: capture
  waveforms and compare equivalent useful-work windows against Python.
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

## How Anoop wants to work

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
- Generated RTL always registers inputs and outputs, so Fmax is a real reg-to-reg number.
  `--pipeline` adds a register after every layer (latency = depth + 2, else 2).
