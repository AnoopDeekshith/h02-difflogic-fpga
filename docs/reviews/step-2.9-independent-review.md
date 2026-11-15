# Step 2.9 independent verification

Reviewed November 14, 2026 by the independent `verify_step_2_9` agent.

## Verdict

No blocking finding remains for reading and cross-checking the saved feasible
candidate's timing. This step revalidates archived evidence; it does not rerun
placement/routing, search for a maximum feasible clock constraint, or measure a
physical board. The two-architecture checklist item remains partial because the
full-layer candidate does not fit and therefore has no routed clock result.

## Independent evidence check

I inspected the original JSON, routing log, generated RTL, parameters, archived
validation record and all nine recorded input/output SHA256 hashes in
`runs/digits_w1000/uart_comb_head/implementation.UVAx2g`.

- The final timing JSON gives **19.3858566284 MHz estimated Fmax** against a
  **12.0000476837 MHz** constraint, consistent with the nominal 12 MHz setting.
- Its same-clock rising-edge path totals **51.5840005875 ns**. Independently
  summing delay categories gives 1.3899999857 ns clock-to-output,
  33.8650004268 ns routing, 15.5050001740 ns combinational logic and
  0.8240000010 ns setup. There are 17 logic and 18 routing segments.
- The reciprocal clock estimate is **51.5839985391 ns**, agreeing with the
  segment sum within report precision. Subtracting it from the constraint's
  83.3330021977 ns period gives **31.7490036586 ns arithmetic margin**. This is
  not an independently reported slack distribution.
- The source is the core input register `l0`, not a learned-layer register.
  The endpoint is in `sc_reg[6]`. Inspection of the RTL exporter supports the
  description of unregistered gate logic and score summation between them.
- The asynchronous button-to-reset path (7.247 ns) and clock-to-UART-output
  path (14.453 ns) are separate from synchronous Fmax. Their presence does not
  establish external I/O constraints or synchronizer MTBF.
- The log contains an earlier 19.18 MHz estimate and a final rounded 19.39 MHz
  estimate. The reader correctly uses the final routed JSON result.
- All nine recorded artifact hashes match. The parent parameter file matches
  the archived synthesis-manifest hash, preventing a later export's parameters
  from being attached to this older route.

I independently ran `scripts/report_timing.py` on both the primary archive and
the earlier independent `implementation.ogVBqL` archive. They yield identical
clock and synchronous-path results. No FPGA executable is needed to read these
archives, and the reader does not rewrite their validation records.

The full-layer plus head-pipeline candidate still needs **6,575/5,280 logic
cells** and its saved attempt has `failed (exit 3)` status. Its missing routed
Fmax must remain unavailable. The original 7.26 MHz timing failure remains
historical evidence in [step 2.8](../steps/2.8-place-and-route.md).

## Code and fault-injection checks

I independently authored [test_timing_report.py](../../tests/test_timing_report.py).
All **18 cases passed**. These cases cover:

- A valid archive with an empty executable search path; reading leaves every
  archive file unchanged and uses the saved tool identity.
- An asynchronous path placed first and made longer than the synchronous path;
  neither ordering nor maximum overall path delay changes the selected Fmax.
- Changed timing, netlist or constraint-file bytes; stale parent parameters;
  and a failed attempt retaining old output files.
- Disagreement between recorded validation and raw clock results; missing or
  duplicate synchronous paths; inconsistent reciprocal period; missing delay
  categories; NaN and negative delays; unmet target; multiple clocks; and
  nonfinite cross-domain delay.
- An older validation record with no optional executable fingerprint. The
  report retains `nextpnr: null` and an explicit limitation, does not alter that
  record, and still rejects changed archived files.

The tests use synthetic archived bundles and do not require installed FPGA
tools or raw gitignored runs. The actual archive checks above are separate
from those fault-injection cases.

## Debug correction checked

The initial reader required a `nextpnr` fingerprint absent from the earlier
independent archive. The corrected reader preserves that absence explicitly
instead of attributing the current machine's executable to the historical run.
I checked the new regression and reran that real older archive. Its file-hash
requirements remain intact. The walkthrough records reproduction, root cause,
fix, verification and prevention using the requested debugging workflow.

## Documentation and research scope

The [step 2.9 walkthrough](../steps/2.9-read-and-verify-clock-timing.md) correctly
explains units, clock conversion, path boundaries, archival provenance, missing
tool metadata and unresolved capacity. Step 2.10 remains responsible for
latency and throughput reporting, with core and UART boundaries distinguished.

This is useful engineering groundwork for holding an implementation and clock
fixed in later experiments. It demonstrates no energy reduction, electrical
power benefit, physical maximum frequency, universal equivalence or research
novelty. Later comparisons still require matched data partitions, FPGA target,
architecture, clock, input sequence and useful work; validation data must select
training settings. Logical activity remains a proxy until supported power or
electrical measurements establish the intended energy result.

Raw implementation files remain local and gitignored. A fresh clone can read
the tracked summary but needs the original artifacts or a reproduced run to
repeat the hash checks. This limitation is stated in the walkthrough.
