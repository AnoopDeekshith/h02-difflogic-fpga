# Discussion record about paper direction, power tools and the professor update

Date: November 19, 2026. Participants: Anoop and the assistant.

This follows [step 4.15](../steps/4.15-test-a-layer-targeted-penalty.md) and the
[step 4.11 board ranking](../results/step-4.11-board-activity-ranking.json).
Questions are quoted verbatim; responses are summarized.

## What the 4.15 result means for the paper

> explain in simple terms what this result means for the paper

- The paper cannot claim a meaningful energy saving from switching-aware
  training. Within the 1-point accuracy rule, mapped core toggles fall by at
  most about 3.6%. That is not energy, and on the UART board it is a tiny
  fraction of switching.
- Layer targeting (last, last two, middle, ramped) did not reliably beat the
  uniform penalty.
- The stronger framing is a **characterization** paper: gate-level switching
  counts overstate the on-chip benefit about five-fold. It shows how much
  survives mapping, routing and glitches, and why, with a bit-exact,
  predeclared, independently reproduced method.
- Correction recorded: an earlier explanation that last-layer gates resist
  because their switching "is the vote" was checked by the verifier and is
  **not supported**. The mechanism is unknown.

## Gray coding

> what about profs mention about grey encoding insted of thermometer encoding?

- Thermometer pixel encoding already changes one bit per brightness step, as
  Gray code does. A 2-bit Gray code would need retraining, and it touches less
  than 1% of board transitions. It would shorten each request from 24 to 16
  image bytes, about 20% less UART time (untested).
- Ranking of the routed board (verified): the three UART counters make ~69% of
  transitions (register bits 21.7%), the clock 27.2% (15.7% if counted once)
  and the network 0.7%.
- Gray-coded counters could at best roughly halve the counter register toggles
  (~11% of board transitions); the effect on next-state logic is unknown.
- A suggestion that prescaling the timeout counter would remove its activity
  was **rejected by review**: the prescaler is itself a fast counter.
- Untested alternatives: run the timeout counter only in the gaps between
  bytes; use a lower clock.

## What could save energy

> what do you think can save energy ? like in this context of the paper?

Expected order of the levers, from measurements but not from energy data:

1. System use: avoid idle time per prediction. Over the UART link a prediction
   takes ~3.4 ms, while inference needs ~250 ns.
2. Glitch reduction: about 1.7 extra transitions per real change in the core.
3. A smaller network.
4. Interface counters (Gray coding or other recoding).
5. The training penalty: about 2–3.5% of core switching, with an accuracy cost.

A device power breakdown is needed to confirm this order.

## Power tools and accuracy

> why is this important and what is the conext of this, explain in very simple and laymen terms

> is vivado not open sourcw? are there any other equivalanet open source  of this which I can measure , i bave one windows laptop myslef

> wait, what are we measuring in vivado? the 0.3 lambda? like the first layer switching?

> how accurate is this compared to on board testing?

- Flip counts treat every transition as equal. A power estimator weights each
  net by its real electrical cost and adds always-on power. It reports static,
  clock, logic and I/O power for the whole design.
- What would be measured: the **whole chip's power** for the λ = 0 control and
  the λ = 0.3 design, each fed the same recorded switching (VCD/SAIF) from the
  same 270 validation images. Not a single layer. Energy per prediction =
  power × time per prediction.
- There is no device-accurate open-source FPGA power estimator, because the
  vendor electrical data is not public.
- **Lattice Radiant**: free node-locked license; Windows and Linux; supports
  the iCE40 UltraPlus (our chip); its Power Calculator can import VCD activity.
  It builds the design with its own tools, so both models must use the same
  Radiant flow.
- **AMD Vivado**: free Standard edition, but for AMD parts (e.g., Artix-7), so
  a separate cross-check experiment.
- Accuracy: absolute estimates are approximate (commonly tens of percent;
  not verified for iCE40). Same-flow comparisons are more reliable, but
  differences around 1% may be within estimator or placement noise. On-board
  USB-meter measurement sees the whole board, so it cannot resolve
  network-level differences.

## Professor update

Anoop asked for the one-pager as a draft in his UCSC email, adding that he
will try Vivado on his x86 Rocky Linux machine. The assistant created a draft
reply in the November 16 thread "Switching-activity regularizer and MCSoC 2027"
to Professor Eshraghian. Anoop then reported:

> i sent it already

The email asked four questions: whether a characterization paper is the right
target and Nov 30 is realistic; whether a device power estimate is essential;
whether a hardware-side follow-up would interest the group more than further
training variants; and whether there is a disclosure concern for Dec 4.

Anoop asked what question 3 means:

> 3. Would a hardware-side follow-up (glitch-aware design, Gray-coded counters) interest your group more than further training variants?

It asks which direction to take next. One option is more training-penalty
variants, where results suggest little headroom. The other is changing the
circuit itself (glitch reduction, Gray-coded counters), where the measured
targets are larger. The choice is the professor's, given his group's work.

## Next steps

- Anoop will configure his x86 Rocky Linux machine on November 20 and continue
  then. Vivado (Artix-7 target) is planned; Radiant (iCE40) is the
  chip-matched option and also runs on Linux.
- The assistant will prepare design files and step-by-step instructions for
  the installed tool once the version and part are known.
- Await the professor's reply before investing in the routed pilot (4.14).
- No energy result exists yet.
