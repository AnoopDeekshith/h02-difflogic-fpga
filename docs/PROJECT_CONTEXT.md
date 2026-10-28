# H02 Project Context

Background for anyone (or any AI assistant) working in this repo.
Last updated: Oct 27, 2026.

## Who and why

- **Anoop**, M.S. ECE at UC Santa Cruz (started Fall 2025, graduating June 2027).
- 4 years of industry experience as a Test and Validation Engineer, so verification is a strength.
- Goal: low-power AI inference hardware. This class project is meant to become his
  **master's project**, lead to a paper, and get him into the professor's neuromorphic research group.
  He pitched this to the professor on Oct 22, 2026.

## The class project (ECE 210, Brain-Inspired Machine Learning)

Professor's project H02: train a small differentiable logic-gate network, discretize
the gates, and map the result into an FPGA workflow.

- **Baseline:** compare three models that must agree:
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
- Closest prior work to differentiate from: "Silicon Aware Neural Networks"
  (arXiv 2604.19334), which uses an area-aware loss and assumes a fixed activity factor.
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

## Status (Oct 27)

- Starter pipeline written; `pytest tests -q` passes (4 tests) on Anoop's laptop,
  including a random-network RTL-vs-Python bit-exact check in Verilator.
- **Not yet run:** the toy training run on 8x8 digits, export, simulation, LUT count.
- **Next:** toy run, then proposal slides for Oct 30.

## How Anoop wants to work

- He is learning this deeply, not just shipping it. The course also asks students to
  understand any AI-suggested fix, not just paste it.
- **Explain step by step**, one small piece at a time, in plain language with an example.
  For each concept cover: What, How, Where it's used, Why, When it matters.
- **Wait for "yes, understood"** before moving to the next piece. Don't dump everything at once.
- Before running long or heavy commands, say what they will do.
- Learning progress so far: (1) logic gates vs. normal neurons, (2) training with a softmax
  mix of 16 rules then discretizing (worked "digit 5" example), (3) exporting to Verilog.
  **Next piece: (4) bit-exact verification**, then FPGA resources/timing, power, the extension.

## Code conventions (see README for layout)

- Gate IDs follow the paper's Table 1. The truth table bits f(0,0) f(0,1) f(1,0) f(1,1),
  read MSB first, equal the gate ID, so `out = (id >> (3 - (2a + b))) & 1`.
- `dlgn/hard.py` is the golden model. RTL must match its integer class scores and its
  argmax, with **ties going to the lowest class index**.
- Model hand-off format is `runs/<name>/model.json` (connections + gate IDs per layer).
- Generated RTL always registers inputs and outputs, so Fmax is a real reg-to-reg number.
  `--pipeline` adds a register after every layer (latency = depth + 2, else 2).
