# Discussion record about switching reduction and research value

Date: November 18, 2026. Participants: Anoop and the assistant.

This records the discussion immediately after step 4.5. The questions below
are quoted verbatim; the responses and research implications are summarized.
Recording this discussion did not run an experiment or complete another
checklist step.

## Does the lambda 0.3 result mean the idea failed

Anoop asked:

> so 0.3 does not work? what we tought about does not work?

The assistant explained that lambda 0.3 achieved one part of the goal:
**lower settled logical switching**. Across the four new model seeds,
switching fell in every pair, averaging **16.71% fewer transitions**.
However, mean validation accuracy fell from **92.41% to 90.93%**, a loss of
**1.48 percentage points**. Only **one of four new pairs** met the frozen
one-percentage-point accuracy allowance.

The conclusion was that lambda 0.3 is not a consistently acceptable default
under our current rule. The experiment supports a lower-switching effect in
these runs; it does not establish the full goal of acceptable accuracy and
lower hardware energy. It also does not establish that the entire research
idea fails.

The assistant initially suggested checking weaker fixed penalties such as
lambda 0.03 or 0.01 across matched seeds. That suggestion was subsequently
reconsidered in the exchange below.

## Is a weaker penalty too small to matter

Anoop asked:

> but doesent 0.03 too low and barely any energy reduction overall which might not be worth to persue it?

The assistant acknowledged this as a real research risk. In the seed-0 sweep,
lambda 0.03 gave only **2.05% fewer logical transitions**, with **0.74
percentage points of accuracy loss**. That is a modest logical result and
has not been demonstrated to produce meaningful energy savings. It is not a
strong main conference result on the available evidence alone.

**The 2.05% figure is a logical-transition reduction, not an energy reduction.**
FPGA power also depends on switched capacitance, voltage, frequency, clock
activity and static consumption. Different transitions need not have equal
energy cost. The existing training metric does not include mapped routing,
capacitance or timing-dependent glitches.

A teaching example made the distinction concrete: if affected logic used
20% of total energy, and its own energy fell by 2%, total energy would fall
by only **0.4%**, with all other energy and the workload unchanged. Both
percentages in that example are hypothetical; neither is a project measurement.
It does not convert our 2.05% logical count into an energy estimate.

## Revised recommendation from the discussion

The assistant explicitly corrected the earlier recommendation to simply try
weaker penalties. The proposed priority became:

1. Establish a supported device-specific power-estimation or electrical
   measurement flow.
2. Make a bounded hardware/energy comparison between matched control and
   lambda-0.3 models, which show the stronger repeated logical-switching
   difference. Use the same target, architecture, clock, ordered inputs,
   workload and completed-prediction accounting; retain accuracy results.
3. Assess whether the measured or estimated energy benefit is large enough
   to justify the observed accuracy cost before investing in more lambda tuning.

This pilot would investigate the surrogate-to-energy relationship. It would
not promote lambda 0.3 as an accuracy-approved model. Report dynamic and total
energy separately, with estimation or measurement limitations made explicit.
RTL equivalence and implementation feasibility are still required for each
new model; a software result does not establish that either model fits or
meets timing.

The one-point allowance is our working experimental target, not a professor
mandate or a universal definition of paper value. Any future change of target
needs a separately recorded comparison. Existing failed accuracy-budget
decisions remain failed under their original rule.

## What remains open

The energy pilot is a **recommendation discussed in this conversation**,
not a completed experiment or a selected power-analysis flow. No new training,
test evaluation, RTL export, FPGA implementation, power estimation or electrical
measurement occurred while recording it. No energy benefit, research novelty
or conference suitability has been established.

The central open question is whether the repeated logical reduction at
lambda 0.3 translates into useful energy savings at a worthwhile accuracy
cost. A small effect, implementation overhead, or an inadequate relationship
between the surrogate and hardware energy could require revising the method
or research direction. Further weaker-penalty training is not automatically
the highest-priority next experiment.

## Evidence and related notes

- [Step 4.4 sweep](../steps/4.4-sweep-penalty-strengths.md) and
  [numerical results](../results/step-4.4-penalty-strength-sweep.json):
  seed-0 lambda-0.03 logical reduction and accuracy cost.
- [Step 4.5 repeats](../steps/4.5-repeat-the-selected-penalty-across-seeds.md),
  [numerical results](../results/step-4.5-repeated-seeds.json) and
  [independent review](../reviews/step-4.5-independent-review.md): primary
  four-new-seed results; discovery seed 0 is excluded from that primary mean.
- [AMD power-analysis guidance](https://docs.amd.com/r/2024.2-English/ug907-vivado-power-analysis-optimization/Power-Optimization-Feature?contentId=m~m2s3AjeThclnKjT9LVjA):
  general power dependencies, consulted during the discussion. This is not
  quantitative power evidence for the iCE40 target or our models.
- [Project context](../PROJECT_CONTEXT.md) and
  [checklist](../PROJECT_CHECKLIST.md): current status and remaining work.
