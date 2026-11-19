# H02 status for Professor Eshraghian: does switching-aware training save FPGA energy?

Anoop, UC Santa Cruz, November 19, 2026. Draft for discussion; not for circulation.

## Question

Can a differentiable logic-gate network (DLGN; Petersen et al., NeurIPS 2022)
be trained to **switch less**, so it uses less energy on an FPGA, while staying
accurate? Setup: 8×8 digits, 4 layers × 1,000 gates, iCE40 UP5K (iCEBreaker),
validation-only selection (test data untouched). Every hardware model matches
the Python model bit for bit.

## What we found

| Stage | Switching reduction, λ = 0.3 vs control | Evidence |
|---|---:|---|
| Software logical gate changes | **16.7%** (mean of 4 seeds) | steps 4.4–4.5 |
| Mapped iCE40 core toggles | **3.2%** (seed 1) | step 4.13 |
| Whole UART board | core is **~0.7%** of board transitions | steps 3.9, 4.11 |

1. **Training works in software,** but costs accuracy: 1.48 points mean loss,
   and only 1 of 4 seeds stays within our predeclared 1-point limit.
2. **About one fifth of the saving survives synthesis.** Yosys packs gates
   into 4-input LUTs, so only about 870 of 4,000 gates remain as their own
   nets. The popcount/adders make about 60% of mapped toggles and barely
   change.
3. **Penalizing particular layers does not fix this.** Last-layer-only,
   last-two, middle-two and ramped penalties, 28 models, frozen protocol:
   none reliably beat the uniform penalty. Within 1 point of accuracy, mapped
   core toggles fell by at most ~3.6%. The last layer barely responds to
   the penalty; why is unknown.
4. **Glitches and the interface dominate.** In the routed board, glitches add
   ~1.7 transitions per real change in the core. The UART's counters (~69%)
   and the clock (27%) produce almost all board transitions; the network ~0.7%. On this board the network is
   idle most of the time (one image per ~3.4 ms, inference ~250 ns).

All figures are **switching counts, not energy**. We have no power estimate
yet (Radiant/Vivado need an x86 machine).

## Proposed paper framing (characterization)

> Switching-aware DLGN training looks effective at the gate level but
> overstates the on-chip benefit about five-fold. We quantify how much survives
> technology mapping, routing and glitches, and show the larger levers are
> hardware and system design (glitch reduction, interface counters, clocking,
> utilization), not the training objective.

Strengths: bit-exact verification chain, predeclared stop rules, independent
reproduction, failures reported. Limits: one toy dataset, one network size,
one FPGA family, no measured energy.

## Gray coding (your suggestion)

Ranking of the routed UART board's transitions (step 3.9 trace, 8 requests,
independently checked; counts, not energy):

| Block | Share of board transitions |
|---|---:|
| Three UART counters (timeout counter, RX and TX bit timers) | **~69%** (register bits 21.7%, rest next-state/carry logic) |
| Clock (pad and global net; 15.7% if counted once) | 27.2% |
| DLGN network core | **0.7%** |

- **Pixels:** thermometer encoding already changes one bit per brightness
  step, as Gray code does. A 2-bit Gray code would need retraining (accuracy
  unknown) and touches <1% of board transitions. Its larger effect would be
  shorter requests: 16 instead of 24 image bytes, about 20% less UART time
  per prediction (untested).
- **Counters:** Gray-coded counters could at best roughly halve the counter
  register-bit toggles (about 11% of board transitions). The effect on their
  next-state logic is unknown and may be worse on iCE40 (untested). Other
  untested options: let the timeout counter run only in the gaps between
  bytes, and lower the clock, since on this serial-bound workload clock
  transitions per prediction scale with frequency.
- These would be **interface** savings, not savings from the learned network.

## Next step on power

Anoop will try Vivado on his x86 Rocky Linux machine and report back. Vivado
targets AMD parts (e.g., Artix-7), so its numbers would be a separate
cross-check. For the iCE40 itself, Lattice Radiant (Linux/Windows, free
license) can import simulation activity (VCD). Estimates are approximate in
absolute terms; same-flow comparisons between models are more reliable.

## Questions for you

1. Is a characterization paper the right target, and is **MCSoC 2027
   (deadline Nov 30)** realistic, or should we aim later with real power data?
2. Do we need at least one **device power estimate** (Radiant for iCE40 or
   Vivado for Artix-7)? Is there a lab x86 machine with either tool?
3. Is a hardware-side follow-up (glitch-aware design, Gray/prescaled
   counters) more interesting to your group than more training variants?
4. Disclosure: any concern about presenting the power idea on Dec 4?
