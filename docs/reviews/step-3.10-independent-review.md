# Step 3.10 independent review: complementary switching metrics

Date: November 16, 2026. Reviewer: independent verification sub-agent.
Production code was not edited.

## Scope

- `scripts/report_switching_metrics.py`
- `tests/test_switching_metrics.py`
- `docs/steps/3.10-report-complementary-switching-metrics.md`
- `docs/results/step-3.10-switching-metrics.json`
- Inputs: `runs/digits_w1000/model.json`, `runs/digits_w1000/x_test_bits.npy`,
  `docs/results/step-3.{6,7,8,9}-*.json`

## Method

1. Wrote a separate NumPy script (`/tmp/v310/check.py`, run with `python -I`)
   that does not import `dlgn` or the step script. It evaluates each gate by
   indexing its 4-entry truth table (`f(0,0) f(0,1) f(1,0) f(1,1)`, MSB first)
   with `2a+b`. From those outputs it computes per-layer p, mean `2p(1−p)`,
   adjacent-change counts and rates, `2m(n−m)/(n(n−1))`, constant-gate
   counts and input-bit rates, plus 2,000 shuffles using its own seed.
   The check script was a temporary file and has not been kept; its outputs
   are recorded below.
1b. Regenerated the result with `scripts/report_switching_metrics.py --out
   /tmp/v310/regen.json`. Compared as key-sorted JSON, it is identical to the
   tracked file, including the category blocks and the seeded shuffle standard
   deviations (overall 0.00327, rounded to 0.0033 in the walkthrough).
2. Derived the random-order formula by hand (below).
3. Compared every number in the walkthrough tables with the cited JSON fields,
   and checked the SHA-256 of the model, the inputs and all four tracked results.
4. Read every claim and compared it with the evidence.
5. Ran the full test suite.

## Findings

### 1. Independent recomputation: matches

All 4 layers, the 4,000-gate aggregate and the 192 input bits match the JSON
exactly (tolerance below 1e-14): surrogate, saved-order changes and rate,
expected rate and constant bits. Saved-order changes are
126,546 / 144,016 / 167,436 / 190,171, with 628,169 in total and 22,013 for
the inputs. These equal the 3.7 RTL values. Constant gates are
220 / 177 / 99 / 3, 499 in total, and 41 input bits are constant. All six
hashes match. The per-gate correlation between `2p(1−p)` and each gate's
saved-order rate is 0.995, and the largest single-gate difference is 0.063.
This is **not independent evidence** that the surrogate is a good proxy. The
surrogate and the measurement use the same 450 hard outputs. For any fixed
image set, the surrogate equals the random-order expectation up to `n/(n−1)`
by construction. The only empirical content is that the saved order behaves
like a random order. Walkthrough conclusions 1 and 2 are therefore one piece
of evidence, not two (non-blocking).

### 2. Random-order formula: correct; "behaves like random" is justified

A gate has m ones among n images. In a uniformly random order, any adjacent
pair of positions holds a uniformly random ordered pair of distinct images.
The chance that the two values differ is
`(m/n)·((n−m)/(n−1)) + ((n−m)/n)·(m/(n−1)) = 2m(n−m)/(n(n−1))`.
By linearity of expectation, this is the expected change rate per pair. It
equals `2p(1−p)·n/(n−1)`.

The saved-order minus expected difference, divided by the shuffle standard
deviation, is 0.70 / 0.76 / 0.72 / 0.80 per layer and 0.74 overall. My own
2,000 shuffles give a z-score of 0.77, and 22.9% of shuffles are at least as
high as the saved order. The claim of "under one standard deviation" holds for
the gates. The input bits are at 1.13 SD; the walkthrough does not claim
otherwise. Caveat: all four layers share one ordering, so they are one draw,
not four independent confirmations.

### 3. Table values against sources: match, with one label defect

- The 3.6 whole-trace category sum is 1,843,155. Its 1,036 identifiers equal
  `whole_trace.unique_identifier_count`.
- The 3.8 mapped whole-trace total is 667,463. Its 3,569 net bits equal
  `mapping.net_bit_count`. The script hardcodes the 1,036 and 3,569 strings
  instead of reading these fields; the values are correct.
- 3.9 core: 20,402 / 12,178 = 1.6753 over 3,252 nets.
- 3.9 non-clock totals: 1,220,880 / 2,265,499 = 0.5389 over **4,321** nets.

The walkthrough is correct. **Defect:** the JSON table row
"all non-clock" says "4,323 routed UART-board net bits"
(`docs/results/step-3.10-switching-metrics.json:279`), produced at
`scripts/report_switching_metrics.py:124` from `observed_net_bits`. That
count includes the 2 clock nets. The row should use
`timed['totals']['nets']` (4,321).

### 4. Claim bounding

- **Blocking.** `docs/steps/3.10-report-complementary-switching-metrics.md:40-41`
  says "Most of the gap is the finite-sample factor n/(n−1). The rest comes
  from this particular order." This is false. Overall, the gap from surrogate
  to measured is 0.00320, and the finite-sample part is only 0.00077 (24%).
  Each layer is between 23% and 25%. About 76% of the gap is the order
  deviation, which is itself within shuffle noise. Suggested wording: about a
  quarter comes from the `n/(n−1)` factor, and the remainder is order
  deviation within the shuffle spread.
- **Minor (contradiction).** `scripts/report_switching_metrics.py:140` and
  JSON `:294` say the saved order differs "because neighbouring test images
  are correlated or anti-correlated". This is a causal claim, and finding 2
  contradicts it: the deviation is consistent with chance. Suggested wording:
  "the saved-order deviation is within the permutation spread".
- "Within 1% in every layer" is true, but barely: the relative gaps are
  0.87–0.98%. The depth trend (0.28 to 0.42) and "496 of 499 constant gates in
  layers 1–3" are stated as observations and left unexplained. Acceptable.
- "Misses ~63%": the arithmetic checks out (20,402 / 32,580 = 62.6%). It is
  scoped to the routed core and 8 images and framed as needing a 4.x test.
  **Minor wording issue (population swap):** the 3.9 `core` category is
  3,252 routed board nets. They include the LUT-packed layers, popcount/carry,
  score registers and argmax (3.9 walkthrough line 63), not the 4,000 logical
  gate outputs that `2p(1−p)` models. Lines 50–53 should say that the ratio
  applies to routed core nets. They should not imply that the surrogate's own
  population misses 63%. Also note that Icarus delays are inertial: pulses
  narrower than a path delay are dropped (3.9 semantics).
- The populations-not-interchangeable and not-energy limits are present.
  The surrogate-as-proxy conclusion is scoped with "here". It is supported by
  the per-gate correlation.

### 5. Tests

`.venv/bin/python -m pytest tests -q`: **255 passed in 13.12 s**, no skips or
failures. Note that the 3.10 tests use a fake 3.9 fixture, so the 3.9-derived
table values are verified only by this review.

## Verdict

**Blocking, one fix required:** walkthrough lines 40–41 misattribute the gap.
Also fix the 4,323→4,321 label (script:124), the causal interpretation
string (script:140) and the 63% population wording (walkthrough:50–53). Then regenerate the JSON. No numeric computation is wrong.
After those text fixes, the step can pass.

## Recheck after fixes (final verdict)

- **Walkthrough "What this shows" point 1:** the gap is now split correctly:
  0.00077 from `n/(n−1)` (24%) and 0.00243 from the order (76%, within shuffle
  noise). This matches my recomputation. The blocking finding is resolved.
- **Point 2:** now notes that points 1 and 2 are not independent evidence.
  **Point 4:** the 63% is now limited to the 3.9 core nets, and the text says
  those nets include popcount, score and argmax logic. Resolved.
- **Script line 140 / JSON line 294:** the causal "because correlated" wording
  is replaced by "within shuffle noise".
- **JSON line 279:** now 4,321 non-clock net bits.
- **Regeneration:** a fresh run to `/tmp/v310/regen2.json` is identical to the
  tracked JSON when both are compared as key-sorted JSON.
- **Tests:** `.venv/bin/python -m pytest tests -q`: 255 passed in 13.94 s.

**Final verdict: PASS.** No blocking findings remain. Non-blocking notes still
open:
- the 1,036 and 3,569 strings are hardcoded in the script (values correct);
- the 3.10 tests use a fake 3.9 fixture;
- the walkthrough "Status" line should be updated to say the step is
  independently verified.
