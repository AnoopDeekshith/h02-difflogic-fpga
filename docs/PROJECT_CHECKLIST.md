# H02 Project Checklist

Saved from Anoop's supplied checklist on November 13, 2026. Initially a snapshot;
items 2.5–2.7 were subsequently updated after tool, UART and constraint checks.
Completed-step explanations start at [the learning index](steps/README.md).

We have completed the toy model, functional verification, and FPGA synthesis. Switching measurements, timing analysis, energy experiments, and physical deployment remain.

This checklist reflects the code and saved results as of November 14, 2026.
New steps require an independent verification sub-agent and a recorded review.

Status: ✅ Completed · ◐ Code exists, validation remains · ☐ Pending

The first part establishes that the trained network works and that its Verilog implementation computes the same result.

| ID | Task | Status | Specific result or remaining work |
|---|---|---|---|
| 1.1 | [Prepare the toy dataset](steps/1.1-prepare-the-digits-data.md) | ✅ | 8×8 handwritten digits; each pixel encoded using three thresholds, giving 192 input bits per image. |
| 1.2 | [Implement the 16 two-input logic gates](steps/1.2-implement-the-logic-gates.md) | ✅ | Truth tables, differentiable formulas, and Verilog expressions implemented. Gate tests pass. |
| 1.3 | [Implement the trainable network](steps/1.3-build-the-trainable-network.md) | ✅ | Soft gate selection, fixed connections, and class-score calculation implemented. |
| 1.4 | [Train the baseline](steps/1.4-train-the-baseline.md) | ✅ | 4 layers × 1,000 gates, 60 epochs, seed 0, switching penalty disabled. |
| 1.5 | [Lock each gate to one rule](steps/1.5-lock-the-gates.md) | ✅ | Discretized network saved in runs/digits_w1000/model.json. |
| 1.6 | [Measure recognition accuracy](steps/1.6-measure-recognition-accuracy.md) | ✅ | Soft: 93.78%; hard: 93.56%; loss from discretization: 0.22 percentage points. |
| 1.7 | [Build the independent Python reference](steps/1.7-build-the-python-reference.md) | ✅ | NumPy implementation computes gate outputs, integer class scores, and predictions. Hard PyTorch scores match it. |
| 1.8 | [Export the original Verilog design](steps/1.8-export-the-verilog-core.md) | ✅ | Input/output registers, logic layers, score calculation, predicted class, and valid signals generated. |
| 1.9 | [Generate reference vectors and a self-checking testbench](steps/1.9-generate-reference-vectors.md) | ✅ | Testbench compares every class score and the predicted class against Python. |
| 1.10 | [Verify the trained model in simulation](steps/1.10-verify-the-core-bit-for-bit.md) | ✅ | 450/450 images match exactly. This covers those inputs; it is not formal verification over every possible input. |
| 1.11 | [Run the existing regression tests](steps/1.11-run-the-regression-tests.md) | ✅ | 45 tests pass: 14 earlier cases, 16 independently written exhaustive head-pipeline cases, 11 artifact and 4 data-partition cases. See independent review for scope. |

The second part establishes the FPGA resource cost and achievable performance.

| ID | Task | Status | Specific result or remaining work |
|---|---|---|---|
| 2.1 | [Synthesize the original design for iCE40](steps/2.1-synthesize-the-original-core.md) | ✅ | 2,929 LUT4s, 268 flip-flops, 123 carry cells. Latency: 2 cycles. |
| 2.2 | [Export the pipelined design](steps/2.2-add-pipeline-registers.md) | ✅ | Added registers after each of the four logic layers. Latency: 6 cycles. |
| 2.3 | [Verify the pipelined design](steps/2.3-verify-the-pipelined-core.md) | ✅ | 450/450 images match exactly, including scores and predictions. |
| 2.4 | [Synthesize the pipelined design](steps/2.4-synthesize-the-pipelined-core.md) | ✅ | 4,528 LUT4s, 3,523 flip-flops, 123 carry cells. |
| 2.5 | [Establish the timing-analysis flow](steps/2.5-establish-the-fpga-tool-flow.md) | ✅ | Selected iCE40UP5K/SG48 and Yosys → nextpnr-ice40 → IceStorm. Installed nextpnr/IceStorm; counter check passed synthesis, placement/routing, 12 MHz timing, and bitstream generation. Run `bash synth/check_ice40_flow.sh`. This does not establish DLGN timing or board operation. |
| 2.6 | [Prepare a usable top-level interface](steps/2.6-build-the-uart-interface.md) | ✅ | Four-pin UART board top implemented. Each request carries 24 encoded image bytes; each reply carries the class and 10 scores. Both architectures pass 450/450 serial images and synthesize. See `docs/UART_INTERFACE.md`. Physical fit/timing are pending. |
| 2.7 | [Add clock and implementation constraints](steps/2.7-clock-and-pin-constraints.md) | ✅ | Explicit 12 MHz SDC clock plus all four PCF pins accepted by nextpnr. Mapped RX/reset synchronizer connections checked; no timing exceptions. Packing checked for both versions. See step 2.7 learning note for scope and capacity result. |
| 2.8 | [Place and route both architectures](steps/2.8-place-and-route.md) | ◐ | Original routed but failed 12 MHz (7.26 MHz estimate). Corrected head-only pipeline/atomic-input candidate routes at 12 MHz using 4,160/5,280 cells; independently reproduced. Current full-layer+head candidate needs 6,575 cells and cannot fit. |
| 2.9 | Measure maximum clock frequency | ◐ | Corrected candidate has a 19.3858566 MHz routed estimate at the fixed 12 MHz target. Other full-layer candidate is oversized. Consolidated scope/performance reporting and physical validation remain distinct. |
| 2.10 | Compare performance | ☐ | Report clock frequency, latency in cycles and time, and predictions per second for both architectures. |

The third part measures switching before we claim any energy improvement.

| ID | Task | Status | Specific result or remaining work |
|---|---|---|---|
| 3.1 | [Count logical gate changes in Python](steps/3.1-measure-python-switching.md) | ✅ | Baseline average: 0.34976 changes per gate per image transition, using the saved test order. |
| 3.2 | Implement waveform recording | ◐ | DUMP=1 support exists in the simulator script and testbench. No saved VCD waveform was found. |
| 3.3 | Generate baseline waveforms | ☐ | Run the original design with waveform recording enabled and preserve the input sequence. |
| 3.4 | Implement waveform activity analysis | ☐ | Count signal transitions, avoid counting aliases twice, and handle unknown values explicitly. |
| 3.5 | Define the measurement window | ☐ | Exclude reset and startup; account for pipeline fill and drain so comparisons cover equivalent useful work. |
| 3.6 | Separate activity categories | ☐ | Report logical-layer activity separately from registers, clock, control, and output logic where observable. |
| 3.7 | Cross-check Python and RTL activity | ☐ | Compare corresponding settled logical outputs under the same image order. Explain discrepancies. |
| 3.8 | Measure mapped hardware activity | ☐ | Extend beyond logical gates to signals in the synthesized or implemented design. |
| 3.9 | Assess glitch activity | ☐ | Use an appropriate timing-aware simulation flow if supported. Ordinary RTL traces cannot establish physical glitch activity. |

The fourth part is your switching-aware training extension.

| ID | Task | Status | Specific result or remaining work |
|---|---|---|---|
| 4.1 | Implement the training penalty | ◐ | Code supports λ × mean[2p(1−p)], an IID zero-delay surrogate. One-epoch smoke validates execution only; effectiveness and energy correlation remain untested. Future runs use validation monitoring and saved partitions/checkpoints. |
| 4.2 | [Preserve the unpenalized baseline](steps/4.2-preserve-the-unpenalized-baseline.md) | ✅ | Existing run uses λ = 0 and has saved accuracy, model, and logical switching results. |
| 4.3 | Run an initial penalized experiment | ☐ | Train the same network with a small nonzero λ, holding the other settings constant. |
| 4.4 | Sweep penalty strengths | ☐ | Compare several λ values using validation data for selection; reserve test results for final evaluation. |
| 4.5 | Repeat selected experiments across seeds | ☐ | Check that improvements are reproducible rather than dependent on one initialization. |
| 4.6 | Verify each selected model | ☐ | Export each model and repeat score-and-class comparisons against its own Python reference. |
| 4.7 | Measure each model’s hardware cost and activity | ☐ | Compare accuracy, switching, LUTs, registers, and timing using a consistent procedure. |
| 4.8 | Plot the tradeoffs | ☐ | Accuracy versus switching first; accuracy versus estimated or measured energy once available. |
| 4.9 | Run the optional penalty ablation | ◐ | Per-sample penalty mode exists, but no experiment has compared it with the batch-mean switching penalty. |

The fifth part turns activity measurements into power and energy evidence.

| ID | Task | Status | Specific result or remaining work |
|---|---|---|---|
| 5.1 | Select a supported power-analysis flow | ☐ | Confirm the FPGA target, software, and activity-file format. The notes propose Vivado for detailed power analysis, but this is not configured. |
| 5.2 | Supply representative switching activity | ☐ | Import simulation activity and check which implemented signals receive it and which use tool defaults. |
| 5.3 | Estimate baseline power | ☐ | Record operating conditions and report static and dynamic power separately, including the tool’s component breakdown. |
| 5.4 | Estimate optimized-model power | ☐ | Use the same target, clock, workload, and analysis settings as the baseline. |
| 5.5 | Calculate energy per prediction | ☐ | Divide the stated power quantity by sustained predictions per second; distinguish total energy from dynamic-only energy. |
| 5.6 | Establish whether the extension succeeds | ☐ | Quantify energy reduction alongside accuracy, area, and performance changes. No energy reduction has been demonstrated yet. |

Physical deployment is a separate branch. It is not required to continue simulation, but it is needed for an actual FPGA demo and electrical measurements.

| ID | Task | Status | Specific result or remaining work |
|---|---|---|---|
| 6.1 | Confirm the available board | ☐ | Notes list an iCEBreaker/iCE40 UP5K; physical availability and connection have not been checked in this session. |
| 6.2 | Implement host-to-board communication | ◐ | FPGA UART adapter and packet format implemented; a serial host client and live connection remain pending. |
| 6.3 | Verify the complete board design | ◐ | UART pins, board reset, image assembly, core inference, and serial results pass end-to-end simulation. Host integration and physical-board checks remain pending. |
| 6.4 | Generate and program a bitstream | ☐ | Complete board-specific constraints, placement/routing, timing checks, and programming. |
| 6.5 | Compare board predictions against Python | ☐ | Send known test images and record exact prediction agreement. |
| 6.6 | Set up electrical power measurement | ☐ | Identify measurement equipment and whether we can measure an FPGA supply rail or only whole-board power. |
| 6.7 | Compare physical energy consumption | ☐ | Run identical workloads and record power, runtime, and predictions for baseline and optimized designs. |

Finally, we need a reproducible experiment package and the course deliverables.

| ID | Task | Status | Specific result or remaining work |
|---|---|---|---|
| 7.1 | [Maintain current project notes](steps/7.1-maintain-project-notes.md) | ✅ | Project context (docs/PROJECT_CONTEXT.md) contains the verified baseline and architecture comparison. |
| 7.2 | Automate experiment summaries | ☐ | Collect configuration, seed, accuracy, switching, resources, timing, and power into a consistent results table. |
| 7.3 | Preserve reproducible artifacts | ◐ | Local models and logs exist, but runs/ is gitignored. Decide how final artifacts will be archived. |
| 7.4 | Expand beyond the toy dataset | ◐ | MNIST loading and training support exist; no saved MNIST experiment was found. Larger experiments follow the working baseline. |
| 7.5 | Prepare the final report, plots, slides, and demo | ☐ | Recorded final submission/presentation date: December 4, 2026. Existing proposal materials were not found in this repository. |
