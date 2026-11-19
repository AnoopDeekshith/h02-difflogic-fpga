# Project learning notes

Start at step 1.1 and follow the previous/next links, or jump to a topic below.
These notes explain completed work and the current partially completed implementation
step; the [project checklist](../PROJECT_CHECKLIST.md) records exact status.

Each note covers why, what, how, a small example, evidence, code and limitations.
A completed learning note does not imply hardware deployment or energy reduction.

## Documented steps

| Step | Read this note |
|---|---|
| 1.1 | [Prepare the digits data](1.1-prepare-the-digits-data.md) |
| 1.2 | [Implement the 16 logic gates](1.2-implement-the-logic-gates.md) |
| 1.3 | [Build the trainable network](1.3-build-the-trainable-network.md) |
| 1.4 | [Train the baseline](1.4-train-the-baseline.md) |
| 1.5 | [Lock the gates to fixed rules](1.5-lock-the-gates.md) |
| 1.6 | [Measure recognition accuracy](1.6-measure-recognition-accuracy.md) |
| 1.7 | [Build the independent Python reference](1.7-build-the-python-reference.md) |
| 1.8 | [Export the Verilog core](1.8-export-the-verilog-core.md) |
| 1.9 | [Generate reference vectors and a testbench](1.9-generate-reference-vectors.md) |
| 1.10 | [Verify the core bit for bit](1.10-verify-the-core-bit-for-bit.md) |
| 1.11 | [Run the regression tests](1.11-run-the-regression-tests.md) |
| 2.1 | [Synthesize the original core](2.1-synthesize-the-original-core.md) |
| 2.2 | [Add pipeline registers](2.2-add-pipeline-registers.md) |
| 2.3 | [Verify the pipelined core](2.3-verify-the-pipelined-core.md) |
| 2.4 | [Synthesize the pipelined core](2.4-synthesize-the-pipelined-core.md) |
| 2.5 | [Establish the FPGA tool flow](2.5-establish-the-fpga-tool-flow.md) |
| 2.6 | [Build the UART board interface](2.6-build-the-uart-interface.md) |
| 2.7 | [Clock and pin constraints](2.7-clock-and-pin-constraints.md) |
| 2.8 | [Placement/routing, timing fix and independent research review](2.8-place-and-route.md) — feasible candidate passes; full layer pipeline remains oversized |
| 2.9 | [Read and verify the maximum-clock estimate](2.9-read-and-verify-clock-timing.md) — feasible candidate's timing audited; full layer alternative remains unavailable |
| 2.10 | [Compare latency and throughput](2.10-compare-latency-and-throughput.md) — core/UART report verified; full layer physical rate unavailable |
| 3.1 | [Measure logical switching in Python](3.1-measure-python-switching.md) |
| 3.2 | [Verify waveform recording](3.2-verify-waveform-recording.md) — short Icarus recording check; full capture is documented in 3.3 |
| 3.3 | [Capture the full baseline waveform](3.3-capture-the-baseline-waveform.md) — all 450 ordered images, head-only core, nominal 12 MHz |
| 3.4 | [Count waveform transitions](3.4-count-waveform-transitions.md) — verified raw bit counter; categories and settled logical comparison are documented in 3.6–3.7 |
| 3.5 | [Define and verify measurement windows](3.5-define-activity-windows.md) — stage-aligned 450 known states/449 adjacent pairs, with input protocol/fill/drain checks |
| 3.6 | [Separate activity categories](3.6-separate-activity-categories.md) — exclusive raw-ID categories and canonical settled layer activity; direct NumPy comparison is documented in 3.7 |
| 3.7 | [Cross-check NumPy and RTL activity](3.7-cross-check-numpy-and-rtl-activity.md) — independently verified exact settled states, transition masks and per-gate counts across all 450 images |
| 3.8 | [Measure mapped hardware activity](3.8-measure-mapped-activity.md) — independently verified mapped net-bit activity, zero-delay |
| 3.9 | [Assess glitch activity](3.9-assess-glitch-activity.md) — SDF-timed routed board, 8 images; core glitch ratio 1.68 |
| 3.10 | [Report complementary switching metrics](3.10-report-complementary-switching-metrics.md) — surrogate vs measured, per layer, RTL/mapped/timed views |
| 4.2 | [Preserve the unpenalized baseline](4.2-preserve-the-unpenalized-baseline.md) |
| 4.3 | [Run the initial matched penalty experiment](4.3-run-the-initial-penalty-experiment.md) — independently verified 60-epoch pair; lower logical switching but accuracy-budget rejection |
| 4.4 | [Sweep penalty strengths](4.4-sweep-penalty-strengths.md) — independently verified eight-point seed-0 grid; lambda 0.3 meets the validation accuracy allowance with lower logical switching |
| 4.5 | [Repeat the selected penalty across seeds](4.5-repeat-the-selected-penalty-across-seeds.md) — independently verified four-new-pair repeat; lower logical switching but only one meets accuracy allowance |
| 4.10 | [Prepare validation-only selection](4.10-prepare-validation-only-selection.md) — independently verified deferred test mode, frozen selection policy, provenance and separate final evaluation |
| 4.12 | [Freeze the hardware-switching stop rule](4.12-freeze-the-hardware-stop-rule.md) — 2% core-level PAUSE/CONTINUE and STOP/PROCEED/INCONCLUSIVE rule, frozen and twice amended before any measurement; independently verified |
| 4.13 | [Run the screening probe](4.13-run-the-screening-probe.md) — seed-1 mapped core toggles fall 3.2% (logical 16.0%); CONTINUE with thin margin; independently verified |
| 4.15 | [Test a layer-targeted penalty](4.15-test-a-layer-targeted-penalty.md) — targeting layers does not reliably beat uniform; chip-level reduction ≤ ~3.6% within accuracy rule; independently verified |
| 7.1 | [Maintain project and learning notes](7.1-maintain-project-notes.md) |

## Older documents

- [November 19 discussion about paper direction, power tools and the professor update](../discussions/2026-11-19-paper-direction-power-tools-and-professor-update.md).
- [November 18 layer-targeted penalty discussion](../discussions/2026-11-18-layer-targeted-penalty.md) and
  [small saving and pilot plan](../discussions/2026-11-18-small-saving-publication-and-pilot-plan.md).
- [November 18 discussion about switching versus energy](../discussions/2026-11-18-switching-versus-energy.md):
  Anoop's questions, the limits of the weak-penalty result and the revised
  recommendation to assess energy benefit before more tuning.

- [PROJECT_CONTEXT.md](../PROJECT_CONTEXT.md): background, goals, results and decisions.
- [PROJECT_CHECKLIST.md](../PROJECT_CHECKLIST.md): completed, partial and pending tasks.
- [UART_INTERFACE.md](../UART_INTERFACE.md): detailed protocol, pins and serial verification.
- [Repository README](../../README.md): setup and quick commands.

## What is not complete

Step 2.8 now has a routed, timing-valid head-pipelined candidate. The full layer
pipeline still exceeds UP5K capacity. Step 2.9 now audits the saved feasible
candidate's timing. Step 2.10 documents cycle latency, core interface capacity
and ideal-host UART performance. The full candidate's physical rate is still
unavailable; it is a capacity failure, not a second implemented benchmark.
Waveform recording has independently checked short Icarus smoke runs and a
full 450-image capture. Raw waveform counting and stage-aligned windows are
verified, including independently reviewed categories and exact settled NumPy/RTL
value/activity agreement. Mapped activity and a scoped timing-aware glitch
assessment are complete. Validation-only training/selection preparation and
its mechanism checks are independently verified. The first matched 60-epoch
penalty pair is independently verified; lambda 0.1 does not meet the accuracy
allowance. The eight-point seed-0 sweep is independently verified;
lambda 0.3 meets that allowance in the discovery seed. The four-new-pair
repeat is independently verified: only one meets the allowance,
so lambda 0.3 is not a robust default. The subsequent discussion linked above
recommends assessing energy benefit before more tuning; that pilot remains
a proposal, not a completed experiment. Selected-model
RTL/hardware checks, power estimates, board programming and electrical
measurements remain pending. The November 16
checklist additions cover complementary metrics (3.10), validation-only
selection (4.10, before the sweep), a separate Gray-coding experiment (4.11)
and professor draft review (7.6). They continue the original plan.
Partial implementation such as the penalty code does not establish an experimental result.

## Keep these notes current

After completing a checklist step, add or update its numbered Markdown note.
Explain what changed, why it matters, how it was checked, the saved evidence,
and what the result does not establish. Link older notes by filename.
Update this index and PROJECT_CHECKLIST.md together.
Every completed step now also needs independent sub-agent verification of code,
methodology, evidence and bounded research relevance. Fix blocking findings and
record the review; see [the step 2.8 review](../reviews/step-2.8-independent-review.md).
