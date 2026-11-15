# Step 2.8: Independent code and research-method review

Reviewer: independent verification sub-agent, November 14, 2026.

## Verdict

The corrected **head-pipelined UART implementation** passes the reviewed
engineering checks for FPGA placement, routing and the 12 MHz clock target.
The reviewer independently reran implementation rather than accepting the
primary agent's reported numbers.

This establishes a usable implemented baseline for further experiments. It
does not establish electrical board operation, physical metastability failure
rates, lower energy, or research novelty. The research direction remains
reasonable if the evaluation conditions below are followed.

## Findings and fixes checked

| Finding | Why it matters | Correction reviewed |
|---|---|---|
| Original design fails 12 MHz timing | A correct RTL simulation cannot make a 7.26 MHz implementation work at 12 MHz | Added a score-register bank and balanced class-winner tree; kept the trained gate rules unchanged |
| Previous scripts relied on exit status and could leave old output files | Old reports could be mistaken for evidence from a new attempt | Fresh attempt directories, input hashes, route/target/timing/capacity checks and explicit status files |
| UART exposed partial images to the inference core | Receiving one image could create many unrelated core transitions | Added an atomic completed-image register; checked the testbench invariant and serial results |
| Training monitored the test set every ten epochs | Model/hyperparameter choices could become influenced by test results | New runs monitor a separate deterministic validation partition; the old digits result stays an exploratory baseline |
| The activity comment equated a probability proxy with SAIF | It could turn a training approximation into an unsupported measurement claim | Corrected the comment to distinguish IID zero-delay surrogate, actual sequence transitions and hardware power |

The class-winner tree was also reviewed logically: each subtree represents a
contiguous ordered class range. Equal scores keep the left winner, so equal
maxima keep the lowest class index even when the class count is odd. Forwarding
an unpaired last subtree does not change that ordering. Both scores and class
outputs use the same registered score bank, preserving their alignment.

## Independent execution evidence

1. Added [test_head_pipeline.py](../../tests/test_head_pipeline.py): **16 cases
   passed**. Each tests all 1,024 possible ten-bit inputs. Cases cover 1, 3, 5
   and 10 classes, layer pipelining on/off, random networks, and deliberately
   tied nonconstant winners. This checks **16,384 input evaluations**, every
   score, the predicted class and the expected 3/6-cycle synthetic latency.
2. Reran the UART/head subset after the atomic image change: **20 cases passed**.
   These overlap the 16 cases above; the counts must not be added together as
   separate unique tests.
3. Independently reran the actual trained head-pipelined UART implementation:
   **4,160/5,280 packed logic cells**, estimated **19.3858566 MHz**, passing the
   approximately **12 MHz** constraint. The actual core latency is **3 cycles**.
4. Tried deliberately corrupted copies of the real result files. The validator
   accepted valid evidence and rejected a 7 MHz timing result, an incomplete
   route flag and a modified synthesized input.
5. Ran a separate one-epoch training smoke experiment in `/tmp`, with width 40,
   depth 2 and activity weight 0.1. It used **1,077 training / 270 validation /
   450 test** images, monitored validation during training, matched hard
   PyTorch/NumPy scores, and saved disjoint split indices plus a checkpoint.
   This checks the corrected training path; its accuracy is not a research
   benchmark or an energy result.
6. Independently ran [simulate_mapped_uart.py](../../scripts/simulate_mapped_uart.py)
   on **3 images** through the synthesized iCE40 cells: every score/class and
   protocol recovery check passed. This uses the actual 104-clock UART divider
   and hardware timeout. It is functional primitive simulation, not routed-delay
   or glitch simulation. Evidence is in
   `runs/digits_w1000/uart_comb_head/mapped_sim.7yoz1h2h/sim.log`.
7. The full suite passed **34 cases** before the artifact tests were added.
   The subsequent artifact/research-protocol subset passed **15 cases**,
   including nine deliberately corrupted implementation bundles and a stale
   synthesis check. These subsets overlap and are not separate unique totals.

The independent implementation evidence is in
`runs/digits_w1000/uart_comb_head/implementation.ogVBqL/`, including
`validated_result.json`, `timing_uart.json`, `routed_uart.json` and
`pnr_uart.log`. The original failed implementation remains in
`runs/digits_w1000/uart_comb/pnr_uart.log`.
These generated files are local and gitignored; final experiment archival is
still required. See the [step 2.8 walkthrough](../steps/2.8-place-and-route.md)
for the maintained reproduction commands.

After tool metadata was finalized, the primary agent reran implementation in
`runs/digits_w1000/uart_comb_head/implementation.UVAx2g/`. The reviewer
independently read this final bundle, checked all archived input/output SHA-256
digests, checked the recorded nextpnr and Yosys binary digests against the local
executables, and confirmed `validated_route_passed` status. It gives the same
19.3858566 MHz and 4,160 logic-cell result. The primary agent's final full-suite
run reports 45 passing tests and its mapped functional run reports 12/12 images;
those are distinct from the reviewer's executions listed above.

The routed JSON places both reset-release registers in tile X21/Y1. RX sampling
stages are at X2/Y5 and X2/Y10; the detailed net report lists approximately
5.309 ns on the interstage path. These are implementation observations, not a
claim of certified synchronizer MTBF or complete asynchronous-interface signoff.

## Sanity check: input order changes switching

On the preserved baseline, the reviewer independently computed:

| Quantity | Value |
|---|---:|
| Hard-output IID proxy, averaged over logical gates | 0.3465578025 |
| Observed transitions in the saved test order | 0.3497600223 |
| Per-gate correlation between those two measures | 0.99528025 |
| Observed transitions after grouping the same images by true label | 0.2387188196 |

No network weights changed in this check. The last row is a diagnostic ordering
experiment, **not** a proposed deployment workload or an optimization result.
It shows why the exact input sequence must be fixed and recorded.

Reproduce from the repository root:

```python
import numpy as np
from dlgn import hard

net = hard.load("runs/digits_w1000/model.json")
x = np.load("runs/digits_w1000/x_test_bits.npy")
y = np.load("runs/digits_w1000/y_test.npy")
h = np.concatenate(hard.forward_bits(net, x), axis=1)
p = h.mean(axis=0)
proxy = 2 * p * (1 - p)
observed = (h[1:] != h[:-1]).mean(axis=0)
order = np.argsort(y, kind="stable")
print(proxy.mean(), observed.mean())
print(np.corrcoef(proxy, observed)[0, 1])
print((h[order][1:] != h[order][:-1]).mean())
```

## Is this a sound research direction?

The bounded question is: **does penalizing a training-time activity proxy reduce
mapped or measured FPGA energy at comparable accuracy?** The current work
builds the machinery to test that question; it has not answered it yet.

Broad novelty must not be claimed. [Silicon Aware Neural Networks](https://arxiv.org/abs/2604.19334)
already trains DLGNs with a hardware-area cost and reports post-layout ASIC
power. [DiffPower](https://arxiv.org/html/2608.03778v1) already uses a
differentiable switching model, including the temporal-independence expression
`2p(1-p)`, for other circuit optimization tasks. A possible narrower contribution
would be validated **DLGN rule-selection training versus mapped FPGA energy**;
whether that is novel requires a fuller literature review and actual results.

Before an energy conclusion, require:

- Baseline and penalized models trained under the same corrected protocol and
  repeated seeds. Select settings using validation, not the already inspected
  digits test results. Do not compare the old full-training-pool baseline with
  new reduced-training-pool models as though only the penalty changed.
- The same FPGA target, head architecture, clock, input sequence, valid pattern
  and measurement window. Serial demo throughput is not core throughput.
- Hard/mapped activity checks, since a soft unweighted gate proxy omits
  synthesis pruning, routing load, glitches, clocks and register power.
- A supported target-specific power flow or calibrated board rail measurement.
  Vivado estimates for an AMD target would be a separate device experiment,
  not measurements of this UP5K implementation.
- Accuracy/area/timing/power tradeoffs and uncertainty, including null results.
  Fewer logical toggles alone do not establish lower joules per prediction.

Lattice documents a Power Calculator for iCE40 UltraPlus in its
[Radiant tutorial](https://www.latticesemi.com/-/media/LatticeSemi/Documents/InstallationGuides/Radiant20_Tutorial_ice40.ashx?document_id=52758).
Its design-aware calculation uses the vendor flow; it should not be assumed to
accept nextpnr JSON directly. [iCEBreaker documentation](https://docs.icebreaker-fpga.org/hardware/icebreaker/)
describes current-measurement provisions, but available equipment and physical
board connections have not been checked here.

Earlier context: [step 2.7](../steps/2.7-clock-and-pin-constraints.md),
[UART_INTERFACE.md](../UART_INTERFACE.md), and
[PROJECT_CONTEXT.md](../PROJECT_CONTEXT.md).
