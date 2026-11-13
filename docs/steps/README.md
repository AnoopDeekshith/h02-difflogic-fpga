# Project learning notes

Start at step 1.1 and follow the previous/next links, or jump to a topic below.
These notes explain completed work; the [project checklist](../PROJECT_CHECKLIST.md) also lists unfinished work.

Each note covers why, what, how, a small example, evidence, code and limitations.
A completed learning note does not imply hardware deployment or energy reduction.

## Completed steps

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
| 3.1 | [Measure logical switching in Python](3.1-measure-python-switching.md) |
| 4.2 | [Preserve the unpenalized baseline](4.2-preserve-the-unpenalized-baseline.md) |
| 7.1 | [Maintain project and learning notes](7.1-maintain-project-notes.md) |

## Older documents

- [PROJECT_CONTEXT.md](../PROJECT_CONTEXT.md): background, goals, results and decisions.
- [PROJECT_CHECKLIST.md](../PROJECT_CHECKLIST.md): completed, partial and pending tasks.
- [UART_INTERFACE.md](../UART_INTERFACE.md): detailed protocol, pins and serial verification.
- [Repository README](../../README.md): setup and quick commands.

## What is not complete

Steps 2.8–2.10 (DLGN placement/routing and performance) remain pending.
Packing in step 2.7 found that the pipelined UART version exceeds UP5K logic-cell capacity.
Waveform activity analysis, switching-aware training experiments, power estimates, board programming and electrical measurements also remain pending.
Partial implementation such as the penalty code does not establish an experimental result.

## Keep these notes current

After completing a checklist step, add or update its numbered Markdown note.
Explain what changed, why it matters, how it was checked, the saved evidence,
and what the result does not establish. Link older notes by filename.
Update this index and PROJECT_CHECKLIST.md together.

