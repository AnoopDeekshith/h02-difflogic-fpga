# Discussion record about a layer-targeted switching penalty

Date: November 18, 2026. Participants: Anoop and the assistant.

This follows the verified [step 4.13 probe](../steps/4.13-run-the-screening-probe.md).
Questions are quoted verbatim; responses are summarized.

## Plain-language explanation of the probe

Anoop asked:

> can you explain what is happening and what was supposed to happenn in suimple and laymen terms?

**Supposed to happen:** train the gates to flip less, so the chip uses less
energy. **In software it worked:** 16% fewer flips at about 1.5 points of
accuracy cost (λ = 0.3). **On the chip:** synthesis packs several gates into
each 4-input LUT, so only about 870 of the 4,000 gates are physical wires. The
counting section (popcount and adders) does about 60% of the chip's flipping
and barely changed. The penalty saved flips mostly in layers 1–2, while layer 4,
which feeds the counting section, changed only 3.6%. The chip therefore
showed only 3.2% fewer flips.

Analogy used: training people on floors 1–2 to switch off lights, while the
building is renovated (rooms merged) and most electricity goes to the top-floor
hall, where nothing changed.

## Should training target later layers

Anoop asked:

> so going forward, should we train on next layers? or th elast layers? you say, that might save even more energy that we initially anticipated? am i reading it right?

Summary of the response:

- Targeting the last layer is a reasonable hypothesis. Each layer-4 flip makes
  the counting section redo part of its addition. A layer-4 saving should
  therefore carry through to the chip better than a layer-1 saving.
- Correction: this would not save more than anticipated. We anticipated about
  16% and got about 3% on the chip. Targeting might recover part of that, an
  unknown amount.
- Risk: layer 4 casts the class votes directly, so restricting it may cost
  accuracy faster than the uniform penalty did.
- The board-level dilution under the UART workload is unchanged (core is about
  0.9% of board transitions in step 3.9).
- Proposed: a cheap test with per-layer penalty weights, a frozen rule, one
  discovery seed with the 25-second chip probe, then confirmation seeds.

## What about the middle layers

Anoop asked:

> yes, set up the last-layer penalty test and also document this discussion. another question beofre we start, what about middle layers? is it worth checking them too?

Response: yes. A layer-4 gate flips when its inputs, which are layer-3 outputs,
flip. Calming layers 2–3 may therefore calm layer 4 and the popcount
indirectly, possibly at a lower accuracy cost than penalizing layer 4 directly.
Which works better is unknown, so a small fixed set of weight profiles is
compared, chosen before results: last only, last two, middle two, and
increasing weights, alongside the existing uniform penalty.

## Plan change

Anoop approved setting up this test as **step 4.15**, before the routed pilot
3.11/4.14. Whichever penalty 4.15 supports is the one worth carrying into the
expensive routed pilot. The 4.12 stop rule and 4.13 result are unchanged.
The frozen plan is
[layer-targeting-v1.json](../experiments/layer-targeting-v1.json). The
proposal that targeting could help is a hypothesis, not a result.
