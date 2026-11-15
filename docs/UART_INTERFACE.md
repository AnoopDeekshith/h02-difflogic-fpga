# iCEBreaker UART interface (checklist 2.6)

The board adapter collects a serial image, submits one request to the existing
`dlgn_top` core, and sends the predicted class and every integer class score.
The core's arithmetic and register configuration are unchanged. Both original
and pipelined exports are supported.

## Physical interface

The top-level module is `board_top`. It specializes `icebreaker_top` for the
exported model. Four signals replace the core's 270-bit external interface:

| Signal | Direction | SG48 pin | Function |
|---|---|---:|---|
| `clk` | Input | 35 | 12 MHz oscillator |
| `button_n` | Input | 10 | Active-low reset button |
| `uart_rx_pin` | Input | 6 | Laptop to FPGA through FTDI |
| `uart_tx_pin` | Output | 9 | FPGA to laptop through FTDI |

References: [iCEBreaker documentation](https://docs.icebreaker-fpga.org/hardware/icebreaker/)
and [Amaranth's board definition](https://github.com/amaranth-lang/amaranth-boards/blob/main/amaranth_boards/icebreaker.py).
Verify the physical board revision before programming. No physical board was
used to validate this interface.

UART uses **115200 baud, 8 data bits, no parity, one stop bit (8N1)**, idle high,
least-significant bit first. At 12 MHz, the integer divider is 104 clocks per
bit (115384.6 baud, approximately +0.16%). The input passes through a two-stage
synchronizer. The reset asserts asynchronously and releases synchronously;
an initialized reset register also provides power-on reset.

## Request and response protocol

Send one complete request, then wait for the entire reply before sending
another. There is no queue or hardware flow control; bytes received while
computing or replying are ignored.

For the current digits model:

```text
Request (26 bytes): A5 5A  image[0] ... image[23]
Reply   (13 bytes): 5A A5  predicted_class  score[0] ... score[9]
```

- Each request carries the already encoded **192 input bits**, not 64 grayscale
  pixel values. Thermometer encoding remains on the laptop.
- Byte 0 contains input bits 0–7, byte 1 contains bits 8–15, and so on. This is
  little-endian packing, consistent with the existing `x.hex` vectors. For
  example, inputs with only bits 0 and 8 set start with image bytes `01 01`.
- Each score occupies one unsigned byte. Scores retain the NumPy reference's
  class order. Ties go to the lowest class index, as in the core.
- The exporter supports other input sizes using `ceil(IN/8)` bytes; unused high
  bits of the final input byte are ignored. It rejects models whose class index
  or maximum class score cannot fit in one byte.
- An incomplete header or image is discarded after approximately **250 ms**
  without a received byte at the 12 MHz hardware clock. Framing errors discard
  partial requests. The header parser accepts overlapping `A5` prefixes.
- The protocol has no checksum or automatic retry. After an incomplete request,
  allow the timeout to expire, or reset the adapter, before retrying. A valid
  UART byte with corrupted data is not detected by the framing checks.

Example packing on the laptop (no serial library needed):

```python
import numpy as np
bits = np.load("runs/digits_w1000/x_test_bits.npy")[0]
request = bytes.fromhex("A5 5A") + np.packbits(bits, bitorder="little").tobytes()
```

A serial host client and actual board inference remain part of step 6.2 onward.

## Export and verify

From the repository root:

```bash
.venv/bin/python scripts/export_uart.py runs/digits_w1000 --sim-clks-per-bit 8
bash sim/run_sim.sh runs/digits_w1000/uart_comb
bash synth/synth_uart_ice40.sh runs/digits_w1000/uart_comb

.venv/bin/python scripts/export_uart.py runs/digits_w1000 --pipeline --sim-clks-per-bit 8
bash sim/run_sim.sh runs/digits_w1000/uart_pipe
bash synth/synth_uart_ice40.sh runs/digits_w1000/uart_pipe

.venv/bin/python -m pytest tests -q
```

The full-dataset simulation can use 8 clocks per bit to finish faster. This
changes only the **testbench parameter**; generated board hardware always uses
104 clocks per bit. Omit the option to simulate the hardware divider instead.
The testbench clock is an arbitrary simulation time base, not an Fmax result.

Each export contains the core, UART RTL, specialized board top, pin constraints,
reference vectors, testbench, and `params.json`. UART simulations use the same
runner as the core simulations. Synthesis writes `synth_uart.json`,
`synth_uart.log`, and `synth_uart_stat.txt`, separate from core-only results.

The serial testbench checks every response byte against NumPy's integer scores
and class predictions. It also tests header noise, overlapping prefixes,
truncated packets, timeout recovery, malformed stop bits, and reset during a
partial request. The focused regression uses the actual 104-cycle divider,
small baud mismatches, non-byte-aligned inputs, zero/all-one inputs, and a model
with tied scores. Full trained-model tests cover all 450 saved test images for
each architecture with the accelerated divider.

## What remains

Follow-up: [step 2.8](steps/2.8-place-and-route.md) adds atomic completed-image
updates and an optional head-pipelined core. The latter routes at the unchanged
12 MHz target using 4,160 cells. `--head-pipeline` exports `uart_comb_head`;
its core has 3 register stages: output availability is 2 elapsed clock periods
after input capture, and downstream register capture is at 3 periods. The packet
layout is unchanged. The older resource
counts below describe the historical step 2.7 versions.

Step 2.7 now integrates explicit clock/pin constraints and checks the synthesized
RX/reset connections. Packing uses 3,795/5,280 logic cells for the original UART
design and 6,236/5,280 for the pipelined version. The latter cannot fit as built.
See [the step 2.7 walkthrough](steps/2.7-clock-and-pin-constraints.md).
Full-layer pipeline resizing remains. [Step 2.10](steps/2.10-compare-latency-and-throughput.md)
now reports core cycle boundaries and UART throughput. The feasible design's
simulated request-start interval is 40,529 clocks, about 296.08 images/s at
12 MHz with the bench's ideal host; USB/OS delays are not modeled.
UART transfer time limits demo throughput;
do not report it as the inference core's maximum throughput. Power experiments
must distinguish this request/response workload from a core processing one
image per clock. The current adapter holds the completed core input during
packet collection; registers remain clocked. It does not add clock gating or
claim energy reduction.
