# Discussion record about small energy savings, publication and pilot plan

Date: November 18, 2026. Participants: Anoop and the assistant.

This continues [switching versus energy](2026-11-18-switching-versus-energy.md).
Questions are quoted verbatim; responses are summarized. Recording this
discussion ran no experiment, power estimate or measurement, and changed no
checklist status.

## Can we check whether switching reduction reduces energy now

Anoop asked:

> SO we do have this problem right now, can you check weather the swicthing reduction produces any energy reductions

The assistant checked the local environment and repository:

- No supported power-analysis tool is installed. Vivado, Lattice Radiant and
  Diamond are absent; Yosys, nextpnr-ice40, IceStorm and Icarus report area,
  timing and activity, not watts.
- No power or energy has been estimated or measured in this project. Steps
  5.1–5.6 are pending.
- Every reduction so far, including the step 4.5 mean of 16.71%, counts
  settled logical transitions. A transition's energy depends on the switched
  capacitance (routing and fanout). Clock, I/O and static power are not
  affected by the penalty.
- The step 3.8 mapped-activity and 3.9 timed-activity scripts are bound to the
  historical model and its saved test-order archive. They cannot measure the
  new matched models without a new, verified path.

**Answer: energy reduction cannot be checked with the current setup.** The
assistant proposed a bounded pilot that needs no new software: export,
place-and-route and simulate matched control and lambda-0.3 models at mapped
and routed-timed levels, comparing fit, timing and (optionally fanout-weighted)
net transitions on identical ordered validation images. It answers whether the
logical reduction survives technology mapping, routing and glitches. It does
not measure energy.

Options for genuine power/energy evidence were listed as unverified candidates:

| Option | Gives | Constraint |
|---|---|---|
| Lattice Radiant | Device power estimate for iCE40 UP5K | Windows/x86-64 Linux only; host Mac is arm64. Simulation-activity import support must be confirmed. |
| Vivado, Artix-7 target | Detailed static/dynamic estimate with simulation activity | Different device and separate experiment; x86 only. |
| iCEBreaker measurement | Measured electrical energy | Needs a measurement point (schematic unchecked), host client and board programming. |

## Is a saving below 2% worth publishing at MCSoC

Anoop asked:

> lets say that it isnt worth persuing it if it is less than 2%, is it still worth publishing in IEEE mcSoc?

Summary of the response:

- A sub-2% energy saving with a mean 1.48-percentage-point accuracy loss is a
  weak headline claim for a power-saving method, especially with related work
  in hardware-aware DLGN training and differentiable power optimization.
- A **characterization paper** could still be a reasonable fit for an
  embedded/SoC venue. Its framing would be: the training penalty reduced
  logical switching by about 17%. The paper reports how much of that remains
  after mapping, routing, glitches and power estimation, and why.
- Supporting reasons: the end-to-end chain is carefully verified (bit-exact
  RTL, mapped and timed activity, then power). A quantified loss of benefit
  informs others, and it identifies what a better method should target.
- Risks: findings of limited benefit are harder to publish. The 2% figure is
  hypothetical, not measured. MCSoC 2027 dates, scope and acceptance
  rate were not verified. Choosing this framing for a first publication is
  the professor's decision (checklist 7.6).

No claim about acceptance, novelty or venue suitability is established.

## Proposed deviations and additional steps

Anoop then asked:

> yes write in discussion and also , lets continue with the next step that we are intended to do. is there any deviation or any extra step needed to be added for this apart from our original plan?

The original plan's next items are 4.6 (verify each selected model in RTL),
4.7 (hardware cost and activity), 4.8 (tradeoff plots) and 5.1–5.6 (power and
energy). The pilot mostly falls inside 4.6–4.7. The assistant identified these
deviations and additions, **proposed and awaiting Anoop's approval**:

1. **Workload uses validation, not test.** `scripts/export.py` reads
   `x_test_bits.npy`; deferred-test runs have no such file, by design. A
   validation-vector export path (saved `x_validation_bits.npy`, fixed order)
   is required. This keeps the test set deferred.
2. **The lambda-0.3 model is carried into hardware as a diagnostic, not as a
   selected model.** Checklist 4.6 says "each selected model"; selection kept
   the control in 4.5. The pilot must label lambda 0.3 as accuracy-failed and
   unselected.
3. **Predeclared stop rule (new).** Write down before seeing results, using
   Anoop's 2% threshold. The logic core is only part of total power, and other
   power is unchanged, so total savings cannot plausibly exceed the core's own
   reduction. If the routed-timed core transition reduction (primary seeds 1–4)
   is below 2%, stop pursuing the energy-saving framing and switch to the
   characterization framing. Otherwise, proceed to a supported power flow
   (5.x). This is a proxy-based gate, not an energy result. A fanout weighting
   is not calibrated capacitance, and area/routing differences must be
   reported alongside it.
4. **Generalize the mapped and timed activity tools (new).** Make the
   step 3.8/3.9 capture and analysis accept any model plus its ordered
   validation workload. Do the previously deferred VCD parser/validator
   consolidation first, since that was flagged for before larger
   hardware-activity batches.
5. **Capacitance proxy metric (new).** Report raw net transitions and
   fanout-weighted transitions separately. Neither is energy.
6. **Seeds.** Primary: matched pairs for seeds 1–4, consistent with 4.5. Seed 0
   is secondary because it informed lambda selection. Run zero-delay mapped
   activity on all 270 validation images. Run timed (glitch) simulation on a
   fixed, predeclared image subset if full runs are too slow.
7. **Place-and-route variability (new).** Placement randomness alters routing
   and glitch counts, and can rival a 2% difference. Run several nextpnr
   placement seeds per model and report the spread.
8. **Same implementation for all models.** Use the feasible head-only
   architecture, the same 12 MHz constraints and pins. Each model must fit and
   meet timing; failures are recorded, not dropped.
9. **Power flow in parallel (5.1).** Anoop checks whether the class or lab
   provides an x86 machine with Radiant or Vivado. This is a user action;
   the assistant cannot install licensed vendor tools.

Proposed order: commit pending verified work, record the stop rule, then item
4, then 4.6 for all ten models, 4.7 fit/timing, then mapped/timed activity,
then the decision. Each step keeps independent verification, a learning
walkthrough, a full-suite debug review and a commit.

## Evidence and related notes

- [Previous discussion](2026-11-18-switching-versus-energy.md)
- [Step 4.5 repeats](../steps/4.5-repeat-the-selected-penalty-across-seeds.md)
  and [results](../results/step-4.5-repeated-seeds.json)
- [Step 3.8 mapped activity](../steps/3.8-measure-mapped-activity.md) and
  [step 3.9 glitches](../steps/3.9-assess-glitch-activity.md)
- [Checklist](../PROJECT_CHECKLIST.md) and [project context](../PROJECT_CONTEXT.md)
