# Step 2.10 independent verification

Reviewed November 15, 2026 by the independent `verify_step_2_10` agent.

## Verdict

No blocking finding remains in the scoped latency and throughput report.
The feasible head-pipelined candidate has timing-supported cycle equivalents
and an explicitly modeled UART workload. The full-layer candidate has valid
RTL cycle observations but no timing-qualified physical rate because it exceeds
UP5K capacity. The two-architecture hardware comparison remains partial.

This review follows the engineering code-review skill and the project's
independent verification requirement. It covers code, methodology, actual
results, terminology corrections and bounded research relevance.

## Independent latency derivation

I traced the generated registers and valid shift chain in
`dlgn/export_verilog.py`. The input captures at edge 0. For the head-only
candidate, scores capture at edge 1 and registered output/valid become available
after edge 2. A downstream register can capture them at edge 3.

Thus `LAT=3` counts register stages. The result is available after **2 elapsed
clock periods** from input capture, and a downstream register captures it after
**3 periods**. These are distinct boundaries, not a change to the FPGA RTL.
The full-layer plus head-pipeline version analogously has 7 stages, 6 elapsed
periods to its output, and 7 to downstream capture.

The 166.67 ns and 250 ns figures for the feasible candidate are cycle-based
equivalents at 12 MHz. They are not measured physical signal arrival times;
the functional RTL simulation does not model routed or clock-to-output delays.

## Independent tests

I authored [test_performance_contract.py](../../tests/test_performance_contract.py).
All **8 cases passed**, including:

- Four independent SystemVerilog cycle-contract cases, covering all combinations
  of layer pipelining and head pipelining. Each streams 48 independently
  generated NumPy reference vectors through a 4-layer, 40-gate, 5-class model.
  They check every score and class, post-update output availability, downstream
  capture, consecutive-input II=1, and preservation of invalid bubbles whose
  input data also change. These are 192 synthetic input evaluations, not an
  exhaustive input proof.
- One independent UART boundary case with three exact replies at the real
  104-clock divider. It demonstrates that a sum of directional byte times is
  not a strict transaction-time lower bound: the reply can overlap the final
  request stop-bit tail on the other wire.
- Two cases that compile and run the shipped `rtl/tb_performance.sv` with
  self-contained head-only and layer-plus-head toy exports. Both verify complete
  replies and the final stop-bit boundary, directly exercising the corrected
  DRAIN/busy/ready observation sequence.
- One matched-comparison case that accepts identical evidence, then independently
  changes each model hash, input-array hash, UART divider, request size and reply
  size. The report rejects every mismatch.

These tests do not need the gitignored trained run or installed FPGA synthesis
tools. Simulator-dependent cases require Icarus; a skip would not establish
verification. My targeted run completed with 8 passed and no skips.

The root agent separately ran the complete regression suite after these code
and test changes: **71 passed in 15.14 seconds**, with no skips. That count
includes these 8 cases and the 63 earlier cases; they are not additional unique
tests beyond 71. This is the root's reported full-suite run, distinct from my
independent targeted run and trained-model reruns.

## Independent trained-model rerun

I independently ran `report_performance.measure` with **16 core vectors and
2 UART transactions per candidate**, then checked the matched comparison.
Both candidates use the same model/input-array fingerprints and fresh NumPy
golden vectors. The results agree with the primary 32-vector/3-transaction report:

| Boundary | Head pipeline | Full layer plus head pipeline |
|---|---:|---:|
| Input capture to registered output | 2 periods | 6 periods |
| Input capture to downstream capture | 3 periods | 7 periods |
| Core initiation interval | 1 period | 1 period |
| Request start to full reply stop-bit end | 40,528.5 periods | 40,532.5 periods |
| Ideal-host request-start spacing | 40,529 periods | 40,533 periods |
| Timing-qualified 12 MHz UART workload rate | 296.084285 images/s | Unavailable |

Independent raw evidence is in:

- `runs/digits_w1000/uart_comb_head/performance.sehxe7sf/`
  (`independent-result.json` records both candidates).
- `runs/digits_w1000/uart_pipe_head/performance.94hgikoe/`.

I also used a separately written temporary serial bench with the actual
trained head-only core and checked three complete reference replies. It
independently measured 40,528.5 periods per request-to-reply window. Its own
host waited for adapter idle, giving a slightly different request-start
spacing. That confirms why the reported 40,529-period spacing must be tied to
the shipped benchmark's explicit ideal-host policy rather than treated as a
universal external-host minimum.

## Code, evidence and corrections reviewed

- The reader checks synthesis freshness, archived implementation binding,
  successful timing or explicit capacity failure, and exact regeneration of the
  synthesized core from the selected model. It recomputes the reference vectors
  instead of trusting possibly stale reference hex files.
- The comparison now requires identical trained-model and input-array hashes
  plus matching UART packet settings. This fixes an initial methodological gap
  where two valid individual runs could have represented different functions
  or workloads.
- Fresh simulation folders preserve logs and source/vector/simulator hashes.
  I checked all 20 simulation-file hashes in the tracked primary report against
  their saved raw files, including the final regenerated report with architecture
  metadata and the matching guard. Both final candidates have 32 checked core
  vectors and 3 UART transactions. The archival route checks are separate from the new
  functional cycle simulation; no new placement/routing was performed.
- The head candidate's 12-million-image/s value is a standalone core-interface
  capacity calculation at the timing-supported 12 MHz clock. It is not the
  existing UART board's measured or attainable input rate.
- The full candidate's Fmax, qualified nanosecond values and qualified rates
  remain `null`. Its packing failure requires 6,575 cells where 5,280 exist;
  RTL simulation is not evidence that it can run physically on this FPGA.

The initial benchmark's preserved `performance.ygvi6bc5/sim.log` records
`Missing reply bytes`. The root cause was observing a transient combination
of adapter DRAIN state and transmitter ready during separate nonblocking
updates. The corrected benchmark observes the final byte becoming busy before
its return to ready. The production-bench regressions above independently
exercise that fix. No FPGA RTL behavior changed for this correction.

I reviewed the [walkthrough](../steps/2.10-compare-latency-and-throughput.md):
stage/cycle definitions, UART overlap, host policy, missing full-candidate rate,
reproduction steps and debug explanation agree with the evidence.

## Research direction and limitations

This step is useful groundwork: it distinguishes an inference core kept busy
each clock from the much slower UART request/reply workload. Later power and
energy experiments must measure useful completed predictions inside the same
window as their power measurement. UART-workload power must not be divided by
the standalone core's theoretical interface capacity.

The study still needs fixed data partitions, model/architecture/target/clock,
ordered inputs and workload windows for controlled baseline-versus-penalty
comparisons. Validation data must select training settings. A capacity failure
is an honest feasibility result, not a second timing benchmark.

No physical board throughput, electrical power, energy reduction, universal
equivalence or research novelty is established here. Raw implementation and
simulation artifacts remain local and gitignored; a fresh clone needs those
artifacts or reproduced runs to repeat their hash checks. The self-contained
regressions remain reproducible without them.
