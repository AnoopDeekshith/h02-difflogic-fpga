# H02: Differentiable Logic Gate Networks on FPGA

ECE 210 (Brain-Inspired Machine Learning), UC Santa Cruz.

For simple explanations of completed work, start with the
[step-by-step learning notes](docs/steps/README.md). The
[project checklist](docs/PROJECT_CHECKLIST.md) tracks remaining work.

Train a network where every neuron is a two-input logic gate (Petersen et al.,
"Deep Differentiable Logic Gate Networks", NeurIPS 2022), lock each gate to one
rule, export the result as Verilog, and test that hardware matches software
bit for bit. Extension: measure switching power and train the network to switch less.

## Pipeline

```
train -> discretize -> export -> simulate -> synthesize -> place/route -> timing

Activity, power and energy evaluation are separate experiments, still pending.
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests -q        # core and UART regressions; simulator required
```

## Toy run (8x8 digits, about a minute on a laptop CPU)

```bash
python scripts/train.py --dataset digits --width 1000 --depth 4 --tau 10 --epochs 60 --out runs/digits_new
python scripts/export.py runs/digits_new
bash sim/run_sim.sh runs/digits_new/rtl_comb   # expect: PASS
bash synth/synth_ice40.sh runs/digits_new/rtl_comb   # LUT4 / FF counts for iCE40
```

New training runs monitor a separate validation set and save partition indices
and a checkpoint. Preserve `runs/digits_w1000` as the historical exploratory
baseline; its old training protocol used the full training pool and monitored
test accuracy. Retrain both controls and penalized models under the same new
protocol before research comparisons.

### Validation-only research selection

Use `--defer-test` for every control/candidate training run used in a sweep.
It saves ordered validation inputs, exact NumPy scores/classes, settled switching,
split indices, a final-epoch checkpoint and hashed provenance. Existing output
directories are rejected. The default compatibility mode still evaluates test;
such runs cannot enter the validation-only selector.

```bash
python scripts/train.py --dataset digits --width 1000 --depth 4 --epochs 60 \
  --defer-test --act-weight 0 --out runs/digits_control_v2
python scripts/train.py --dataset digits --width 1000 --depth 4 --epochs 60 \
  --defer-test --act-weight 0.1 --out runs/digits_penalty_v2
python scripts/select_validation_models.py --control runs/digits_control_v2 \
  --candidates runs/digits_penalty_v2 --out runs/digits_selection_v2.json
```

The policy is copied before training: retain models within one percentage point
of the matched control's hard validation accuracy, then minimize settled
validation switching. This is a working tolerance, not a professor requirement.
Include the control in selection; it can win. Different seeds are compared
separately. Settle the experiment design and candidate list before final test
evaluation; after selection, evaluate the saved checkpoint without retraining:

```bash
python scripts/evaluate_selected_model.py --selection runs/digits_selection_v2.json \
  --out runs/digits_selected_test_v2
```

The final evaluation directory contains the selected model and test vectors for
the existing exporters. Validation-only directories deliberately have no test
vectors. See [step 4.10](docs/steps/4.10-prepare-validation-only-selection.md)
for evidence and limits. The new one-epoch smoke runs check this procedure;
they do not establish an optimized model, lower power, or lower energy.

The [five-pair repeated-seed experiment](docs/steps/4.5-repeat-the-selected-penalty-across-seeds.md)
keeps discovery seed 0 separate from four new pairs. Fixed lambda 0.3 lowers
settled logical switching in all four new pairs, but only one meets the frozen
accuracy allowance; it is not a robust default under that rule. Test evaluation
remains deferred. A subsequent [research discussion](docs/discussions/2026-11-18-switching-versus-energy.md)
recommends assessing the energy benefit before more tuning; no energy pilot
has been launched.

## iCEBreaker implementation tool check

The implementation target is the iCEBreaker's iCE40UP5K, SG48 package, using
its 12 MHz oscillator. No physical board is required for this check.
See the [board specifications](https://docs.icebreaker-fpga.org/hardware/icebreaker/).

On macOS, with Yosys already installed:

```bash
brew install nextpnr-ice40  # also installs IceStorm, including icepack
bash synth/check_ice40_flow.sh
```

This synthesizes a small 24-bit counter, places/routes it with fixed clock and
LED pins, checks timing against 12 MHz, and generates a bitstream. It does not
program the board. Results go to `runs/toolchain_smoke/`: `tools.txt`,
`synth.log`, `nextpnr.log`, `timing.json`, `routed.asc`, and `timing_smoke.bin`.
An optional output directory can be passed to the script.

This confirms that the implementation tools work; its frequency result is for
the counter, not the trained network. The network still needs a suitable
interface or timing harness before its own placement/routing and timing run.

## UART board interface

The UART adapter sends encoded images through the board's USB serial link and
returns the class plus all scores. It uses four external signals: clock, reset
button, RX, and TX. No board is needed to verify the serial path in simulation.

```bash
python scripts/export_uart.py runs/digits_w1000 --sim-clks-per-bit 8
bash sim/run_sim.sh runs/digits_w1000/uart_comb
bash synth/synth_uart_ice40.sh runs/digits_w1000/uart_comb
```

Add `--pipeline` to export the pipelined core to `uart_pipe` instead.
The faster testbench divider does not change the hardware's 115200 baud setting.
See [UART interface](docs/UART_INTERFACE.md) for packet layout, pins, tests,
limitations, and the remaining implementation work.

Clock, pin, and synchronizer checks (step 2.7), after UART synthesis:

```bash
bash synth/implement_uart_ice40.sh runs/digits_w1000/uart_comb --pack-only
```

This validates the constraints and packed capacity without placement/routing.
The historical step 2.7 UART designs used 3,795 and 6,236 packed cells respectively.
Current corrected candidates and their independently verified results follow.
See [step 2.7](docs/steps/2.7-clock-and-pin-constraints.md) for the explanation.

## Routed candidate and independent verification

The original design failed the 12 MHz target. The corrected head-pipelined
candidate registers the class scores, balances winner selection and commits
complete UART images atomically. It uses 4,160/5,280 cells and has a routed
19.39 MHz estimate, passing 12 MHz. The current full-layer+head candidate needs
6,575 cells and is rejected for capacity. Neither has been tested on a board.

```bash
python scripts/export_uart.py runs/digits_w1000 --head-pipeline --sim-clks-per-bit 8
bash sim/run_sim.sh runs/digits_w1000/uart_comb_head
bash synth/synth_uart_ice40.sh runs/digits_w1000/uart_comb_head
bash synth/implement_uart_ice40.sh runs/digits_w1000/uart_comb_head
python scripts/simulate_mapped_uart.py runs/digits_w1000/uart_comb_head --n 12
```

Each implementation attempt has fresh artifacts, source hashes and status.
See the [step 2.8 walkthrough](docs/steps/2.8-place-and-route.md),
[independent code/methodology review](docs/reviews/step-2.8-independent-review.md),
and [compact results](docs/results/step-2.8-results.json).
Every future completed step requires an independent verifier, including a
bounded research assessment. No energy reduction or novelty is established yet.

To audit the saved routed clock estimate without rerunning implementation:

```bash
python scripts/report_timing.py runs/digits_w1000/uart_comb_head/implementation.UVAx2g
```

This requires the raw local artifacts, verifies their recorded hashes, and
cross-checks the 51.584 ns synchronous path against the 19.39 MHz estimate.
It preserves the 12 MHz operating target. See [step 2.9](docs/steps/2.9-read-and-verify-clock-timing.md)
and the [tracked timing summary](docs/results/step-2.9-timing.json).

## Latency and UART throughput

The feasible candidate has 3 register stages: its output is available 2 clock
periods after input capture, and a downstream register captures it after 3.
At the qualified 12 MHz, those are cycle-equivalent 166.67 ns and 250 ns.
The core can accept an input each clock; this is separate from UART board
throughput. The ideal-host UART simulation gives 3.377375 ms per transaction
and about 296.08 images/s, with no USB/OS delay modeled.

```bash
python scripts/report_performance.py \
  runs/digits_w1000/uart_comb_head \
  runs/digits_w1000/uart_comb_head/implementation.UVAx2g \
  --comparison runs/digits_w1000/uart_pipe_head \
  runs/digits_w1000/uart_pipe_head/implementation.1iiA0a \
  --out docs/results/step-2.10-performance.json
```

This checks model/workload matching, regenerates NumPy vectors and runs fresh
cycle simulations. The oversized candidate has cycle results only; its physical
time and throughput remain unavailable. See the
[step 2.10 walkthrough](docs/steps/2.10-compare-latency-and-throughput.md) and
[independent review](docs/reviews/step-2.10-independent-review.md).
Next is waveform recording and activity analysis; energy measurements remain pending.

## Layout

| Path | What it does |
|---|---|
| `dlgn/gates.py` | The 16 gates: truth tables, soft formulas, Verilog expressions |
| `dlgn/model.py` | The trainable network (logic layers + group sum), plus the switching-activity penalty |
| `dlgn/hard.py` | Bit-exact NumPy reference model (the "golden model" the RTL must match) |
| `dlgn/export_verilog.py` | Writes `dlgn_top.sv`, a self-checking testbench, and test vectors |
| `dlgn/difflogic_import.py` | Converts a model trained with the official difflogic library |
| `scripts/train.py` | Train, discretize, report soft vs. hard accuracy |
| `scripts/export.py` | Export a trained run to RTL |
| `scripts/export_uart.py` | Export the core with its UART board adapter and serial testbench |
| `scripts/report_timing.py` | Check archived routed timing and its provenance |
| `scripts/report_performance.py` | Measure core/UART cycle boundaries with matched reference vectors |
| `rtl/` | UART receiver/transmitter, board adapter, and serial testbench template |
| `synth/synth_uart_ice40.sh` | Synthesize the complete UART board top |
| `sim/run_sim.sh` | Run the testbench with Verilator, Icarus, or Vivado xsim |
| `tests/` | Gate-table checks and a random-network RTL vs. software check |
