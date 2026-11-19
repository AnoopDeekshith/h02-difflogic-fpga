# H02 Project Checklist

Saved from Anoop's supplied checklist on November 13, 2026. Initially a snapshot;
items 2.5–2.7 were subsequently updated after tool, UART and constraint checks.
Completed-step explanations start at [the learning index](steps/README.md).

We have completed the toy model, functional verification, synthesis, a routed timing/performance report for the feasible candidate, waveform/NumPy activity checks, mapped activity, a bounded timing-aware glitch assessment and independently verified validation-only experiment preparation. The first matched 60-epoch pair is independently verified; the eight-point, seed-0 penalty sweep is independently verified. The full pipeline remains over capacity. The repeated-seed study is independently verified: switching falls in all four new pairs, but lambda 0.3 meets the accuracy allowance in only one. Selected-model hardware checks, energy experiments and physical deployment remain.

This checklist reflects the code and saved results as of November 18, 2026.
New steps require an independent verification sub-agent and a recorded review.

The [November 18 research discussion](discussions/2026-11-18-switching-versus-energy.md)
records concern that weaker penalties may yield too little useful energy
benefit. The revised recommendation is to assess a supported power flow and a
bounded matched hardware-energy pilot before more tuning. This is a proposed
priority change; no experiment was launched and no task status changed by
recording the discussion.

On November 18 Anoop approved four added steps (3.11, 4.12, 4.13, 4.14; see
[pilot plan discussion](discussions/2026-11-18-small-saving-publication-and-pilot-plan.md)),
bringing the checklist to 65 tasks; 4.15 was added the same day after the 4.13 probe (66 tasks; [discussion](discussions/2026-11-18-layer-targeted-penalty.md)). Lambda 0.3 enters hardware as an
accuracy-failed diagnostic, not a selected model. Steps 4.6–4.7 use saved
validation images, never test data, while selection is open.

## Professor-feedback additions (November 16)

Continue the original plan; do not restart step 1.1. Digits images are already
grayscale and currently use three-threshold thermometer encoding. Gray coding
is a different bit representation, to be investigated separately in 4.11.
Preserve the historical baseline and all failed implementation attempts.

Feedback recovered from conversation `01a1e2b2-7d25-7680-95f3-94ff4ccff21d`:
evaluate multiple switching metrics, investigate Gray coding where relevant,
and send a manuscript draft to Professor Eshraghian before submission. This is
the prior conversation's summary of feedback, not a verbatim professor quote.

Execution order: finish recording/activity checks **3.2–3.7**, with metric
reporting in **3.10**; complete the validation-only preparation **4.10 before
4.3–4.5**; retrain a matched unpenalized control and penalized models. Carry
selected models through 4.6–4.8 and mapped activity 3.8. Treat **4.11** as a
separate encoding experiment after baseline activity is understood. Retain
power/energy steps 5.x and deployment 6.x. Start writing in parallel and use
**7.6** for professor review before submission. No original task is removed.

Status: ✅ Completed · ◐ Partially complete; validation or feasibility remains · ☐ Pending

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
| 1.11 | [Run the existing regression tests](steps/1.11-run-the-regression-tests.md) | ✅ | Latest Nov 18 full run: 285 tests pass, no skips (19.18 s). Includes 255 pre-change cases, 23 validation-selection cases and 7 independent step 4.10 review cases. Earlier per-step totals remain historical. |

The second part establishes the FPGA resource cost and achievable performance.

| ID | Task | Status | Specific result or remaining work |
|---|---|---|---|
| 2.1 | [Synthesize the original design for iCE40](steps/2.1-synthesize-the-original-core.md) | ✅ | 2,929 LUT4s, 268 flip-flops, 123 carry cells. Two register stages; one elapsed clock from input capture to output availability. |
| 2.2 | [Export the pipelined design](steps/2.2-add-pipeline-registers.md) | ✅ | Added registers after each of the four logic layers. Six register stages; five elapsed clocks from input capture to output availability. |
| 2.3 | [Verify the pipelined design](steps/2.3-verify-the-pipelined-core.md) | ✅ | 450/450 images match exactly, including scores and predictions. |
| 2.4 | [Synthesize the pipelined design](steps/2.4-synthesize-the-pipelined-core.md) | ✅ | 4,528 LUT4s, 3,523 flip-flops, 123 carry cells. |
| 2.5 | [Establish the timing-analysis flow](steps/2.5-establish-the-fpga-tool-flow.md) | ✅ | Selected iCE40UP5K/SG48 and Yosys → nextpnr-ice40 → IceStorm. Installed nextpnr/IceStorm; counter check passed synthesis, placement/routing, 12 MHz timing, and bitstream generation. Run `bash synth/check_ice40_flow.sh`. This does not establish DLGN timing or board operation. |
| 2.6 | [Prepare a usable top-level interface](steps/2.6-build-the-uart-interface.md) | ✅ | Four-pin UART board top implemented. Each request carries 24 encoded image bytes; each reply carries the class and 10 scores. Both architectures pass 450/450 serial images and synthesize. See `docs/UART_INTERFACE.md`. Physical fit/timing are pending. |
| 2.7 | [Add clock and implementation constraints](steps/2.7-clock-and-pin-constraints.md) | ✅ | Explicit 12 MHz SDC clock plus all four PCF pins accepted by nextpnr. Mapped RX/reset synchronizer connections checked; no timing exceptions. Packing checked for both versions. See step 2.7 learning note for scope and capacity result. |
| 2.8 | [Place and route both architectures](steps/2.8-place-and-route.md) | ◐ | Original routed but failed 12 MHz (7.26 MHz estimate). Corrected head-only pipeline/atomic-input candidate routes at 12 MHz using 4,160/5,280 cells; independently reproduced. Current full-layer+head candidate needs 6,575 cells and cannot fit. |
| 2.9 | [Read and verify maximum-clock timing](steps/2.9-read-and-verify-clock-timing.md) | ◐ | Hash-checked archived report: 19.3858566 MHz estimated Fmax, 51.584 ns synchronous path, passes fixed 12 MHz. Independent archive agrees. Full-layer candidate is oversized and has no routed Fmax; no physical frequency measurement. |
| 2.10 | [Compare latency and throughput](steps/2.10-compare-latency-and-throughput.md) | ◐ | Feasible core: 2 clocks to output, 3 to downstream capture, initiation interval 1 at qualified 12 MHz. UART simulation: 3.377375 ms per request/reply, about 296.08 images/s with an ideal host. Full pipeline: 6/7-cycle behavior checked, but no timing-qualified rate because it cannot fit. |

The third part measures switching before we claim any energy improvement.

| ID | Task | Status | Specific result or remaining work |
|---|---|---|---|
| 3.1 | [Count logical gate changes in Python](steps/3.1-measure-python-switching.md) | ✅ | Baseline average: 0.34976 changes per gate per image transition, using the saved test order. |
| 3.2 | [Verify waveform recording](steps/3.2-verify-waveform-recording.md) | ✅ | Fresh Icarus recording-on/off runs pass 8/8 exact score/class vectors for original and feasible head-only cores; required input/layer/output signals recorded. Independently reproduced; 14 focused tests pass. Short nominal-100-MHz mechanism check only; full baseline capture is documented in 3.3. |
| 3.3 | [Capture full baseline waveforms](steps/3.3-capture-the-baseline-waveform.md) | ✅ | Independently reproduced full capture: 450/450 scores/classes. Historical unpenalized model, feasible head-only core, all saved inputs in original order, standalone streaming at nominal 12 MHz (83,334 ps simulation period). Full VCD input/output/marker decoding and provenance checked; raw reset/fill/drain preserved. |
| 3.4 | [Implement waveform activity analysis](steps/3.4-count-waveform-transitions.md) | ✅ | Digital VCD bit counter groups true aliases by ID, excludes initialization from toggles and separates X/Z changes. 35 independent tests pass; separate per-ID oracle agrees on both full captures. Whole-file diagnostic: 1,843,155 known bit flips; includes markers/control/copies/startup/drain, not a validated useful-work network total or energy result. |
| 3.5 | [Define and verify measurement windows](steps/3.5-define-activity-windows.md) | ✅ | Stage-aligned windows retain 450 known states/449 image pairs each, shifted for register availability; initialization excluded and final outputs retained. Clock/reset/valid/data schedule and held drain verified on both captures. Independent review rechecked the off-phase/drain pulse fix; 22 focused tests pass. These are not one global energy interval; categories and NumPy comparisons are documented in 3.6–3.7. |
| 3.6 | [Separate activity categories](steps/3.6-separate-activity-categories.md) | ✅ | Independently verified exclusive whole-trace ID categories and 14 aligned observations. Canonical settled layers: 628,169 changes / 1,796,000 bit-pair opportunities = 0.34976002; copies excluded. Twenty focused tests pass; separate raw/settled oracles agree on both captures. RTL proxy only; direct NumPy comparison documented in 3.7, no energy claim. |
| 3.7 | [Cross-check Python and RTL activity](steps/3.7-cross-check-numpy-and-rtl-activity.md) | ✅ | Independently verified exact values, transition masks and per-gate counts: 14 observations × 450 images, zero discrepancies, including six tied-score images. Canonical 628,169 changes / 1,796,000 opportunities = 0.34976002, matching fresh NumPy toggle_rate. Twenty-two focused tests pass; fixture-only tie assumption corrected and preserved. No mapped/glitch/power/energy claim. |
| 3.8 | [Measure mapped hardware activity](steps/3.8-measure-mapped-activity.md) | ✅ | Independently verified zero-delay iCE40UP mapped sim: 3,569 net bits, 450/450 exact, 667,463 known whole-trace flips (LUT 569,566), 0 X/Z. Not glitches or energy. |
| 3.9 | [Assess glitch activity](steps/3.9-assess-glitch-activity.md) | ✅ | Independently verified SDF-timed routed UART board, 8 images: core 1.68 extra transitions per settled change (20,402/12,178); interface 0.70. Inertial Icarus model, one delay corner; not energy. |
| 3.10 | [Report complementary switching metrics](steps/3.10-report-complementary-switching-metrics.md) | ✅ | 2p(1−p) 0.3466 vs saved-order 0.3498 vs random-order 0.3473 per gate pair; per-layer 0.28→0.42; 499 constant gates; RTL/mapped/timed views tabled with populations and denominators. |
| 3.11 | Generalize mapped and timed activity tools | ☐ | Added Nov 18; built only if the 4.13 probe says CONTINUE. Accept any model plus its ordered validation workload; consolidate the shared VCD parser/validator; add routed-board core-net classification (exactly category 'core') and reuse the 4.13 standalone M1/M2 code unchanged. Proxy only. |

The fourth part is your switching-aware training extension.

| ID | Task | Status | Specific result or remaining work |
|---|---|---|---|
| 4.1 | Implement the training penalty | ◐ | Code supports λ × mean[2p(1−p)], an IID zero-delay surrogate. Repeated λ=0.3 runs reduce settled validation switching in all four new pairs (mean 16.71%), but only one meets the frozen accuracy allowance; mean loss 1.48 pp. Consistently acceptable accuracy, energy benefit and generality remain unestablished. |
| 4.2 | [Preserve the unpenalized baseline](steps/4.2-preserve-the-unpenalized-baseline.md) | ✅ | Existing run uses λ = 0 and has saved accuracy, model, and logical switching results. |
| 4.3 | [Run an initial penalized experiment](steps/4.3-run-the-initial-penalty-experiment.md) | ✅ | Independently verified fresh matched 60-epoch seed-0 pair. Control: 249/270 hard validation correct, 0.347500 switching. λ=0.1: 245/270, 0.322456 switching (7.21% lower), but 1.48 pp accuracy loss exceeds the frozen 1 pp allowance, so control is retained. Test remains deferred; no energy claim. |
| 4.4 | [Sweep penalty strengths](steps/4.4-sweep-penalty-strengths.md) | ✅ | Independently verified eight-point seed-0 grid. Six new 60-epoch runs plus two explicitly reused 4.3 runs. λ=0.3 selected: 247/270 correct (91.48%) vs control 249/270 (92.22%); 17.17% fewer settled changes with 0.74 pp accuracy loss. Test deferred; one-seed validation choice, not energy evidence. |
| 4.5 | [Repeat selected experiments across seeds](steps/4.5-repeat-the-selected-penalty-across-seeds.md) | ✅ | Eight new 60-epoch runs form paired seeds 1–4 with fixed λ=0.3, plus explicitly reused discovery seed 0. Independently verified methodology, artifacts and aggregation. Primary mean switching reduction 16.71%; mean accuracy loss 1.48 pp; only 1/4 new pairs passes the unchanged allowance. All-pairs consistency fails; no seed discarded or λ retuned. Test deferred; no energy claim. |
| 4.6 | Verify each selected model | ☐ | Export each model and repeat score-and-class comparisons against its own Python reference. |
| 4.7 | Measure each model’s hardware cost and activity | ☐ | Compare accuracy, switching, LUTs, registers, and timing using a consistent procedure. |
| 4.8 | Plot the tradeoffs | ☐ | Accuracy versus switching first; accuracy versus estimated or measured energy once available. |
| 4.9 | Run the optional penalty ablation | ◐ | Per-sample penalty mode exists, but no experiment has compared it with the batch-mean switching penalty. |
| 4.10 | [Prepare validation-only experiment selection](steps/4.10-prepare-validation-only-selection.md) | ✅ | Independently verified deferred test mode, ordered validation data/reference scores/activity, frozen accuracy-budget policy, matched within-seed selector and checkpoint-based final evaluation. Two one-epoch mechanism runs passed; full suite 285 passes. No useful penalty result claimed; the already inspected digits test remains exploratory. |
| 4.11 | Assess Gray coding in a separate experiment | ☐ | First identify candidate pixel/score/counter signals and actual transitions. Current pixel encoding is thermometer. Gray-coded pixel inputs require retraining and explicit input-width/quantization controls; register/counter recoding requires score/class equivalence and area/timing/activity accounting. Separate interface savings from learned-network savings; no automatic benefit is assumed. |
| 4.12 | [Freeze the hardware-switching stop rule](steps/4.12-freeze-the-hardware-stop-rule.md) | ✅ | Added Nov 18. Policy `docs/experiments/hardware-switching-stop-rule-v3.json` (v1 amended twice before measurement after independent review; 2% core-level threshold, M1 raw / M2 fanout-weighted core transitions, STOP/INCONCLUSIVE/PROCEED, PAUSE/CONTINUE probe) frozen before any hardware measurement of the new models; independently verified (three review rounds; v1/v2 kept in git). |
| 4.13 | [Run the screening probe](steps/4.13-run-the-screening-probe.md) | ✅ | Independently verified (rerun hash-identical; separate oracle exact). Seed 1, 270/270 RTL and mapped exact. Logical 16.0% → mapped M1 **3.2%**, M2 **3.9%** (2.37% without input-register load difference). **CONTINUE**, thin margin. Popcount/adders ≈60% of mapped toggles, nearly unchanged; layer-4 logical reduction only 3.6%. Not energy. |
| 4.14 | Run the hardware switching pilot | ☐ | Added Nov 18; only after CONTINUE. Seeds 1–4 primary, seed 0 secondary, routed SDF-timed core activity, placement seeds 1–3, noise check, final STOP/INCONCLUSIVE/PROCEED. Not an energy result. |
| 4.15 | Test a layer-targeted switching penalty | ☐ | Added Nov 18 after 4.13; runs before 3.11/4.14. Frozen plan `docs/experiments/layer-targeting-v1.json`: profiles L4, L34, M23, RAMP vs uniform at λ 0.1/0.2/0.3 (same grid for all); seed-1 discovery by lowest mapped M1 within 1 pp; confirmation seeds 2–4; TARGETING_BETTER only if every seed is eligible, ≥ 2% and beats the comparator. Backward compatibility: retrained seed-1 control/λ0.3 byte-identical. Not energy. |

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
| 7.6 | Send manuscript draft for professor review | ☐ | Write alongside experiments; send Professor Eshraghian a concrete draft with figures, measurement definitions, limitations and open questions before submission. Prior discussion targeted MCSoC 2027/November 30; independently verify venue dates before submission. Sending requires explicit user authorization. |
