"""Measure RTL cycle latency and ideal-host UART transactions with bound evidence."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dlgn import hard
from dlgn.export_verilog import emit_rtl, write_vectors
from build_artifacts import check_synth, digest
from report_timing import summarize as timing_summary


def implementation_evidence(folder, attempt):
    """Accept a valid routed result or an explicitly evidenced capacity failure."""
    if attempt.parent.resolve() != folder.resolve():
        raise ValueError("Implementation attempt must belong to the supplied export")
    check_synth(folder)
    for name in ("synth_uart.json", "synth_manifest.json"):
        if digest(folder/name) != digest(attempt/name):
            raise ValueError(f"Export differs from archived implementation: {name}")
    status = (attempt/"status.txt").read_text().strip()
    if status == "validated_route_passed":
        timing = timing_summary(attempt)
        return dict(outcome="routed_timing_passed", timing_qualified=True,
                    estimated_fmax_mhz=timing["estimated_fmax_mhz"],
                    utilization=timing["utilization"],
                    provenance=timing["provenance"])
    if status != "failed (exit 3)":
        raise ValueError(f"Unsupported or incomplete implementation status: {status}")
    capacity = json.loads((attempt/"pack_uart_report.json").read_text())["utilization"]
    audit = json.loads((attempt/"constraint_audit.json").read_text())
    lc = capacity["ICESTORM_LC"]
    if audit["within_resource_capacity"] or audit["packed_utilization"] != capacity or lc["used"] <= lc["available"]:
        raise ValueError("Failed status does not establish logic-cell capacity failure")
    if audit["target"] != "iCE40UP5K-SG48" or lc["available"] != 5280:
        raise ValueError("Unexpected capacity target")
    return dict(outcome="capacity_exceeded", timing_qualified=False,
                estimated_fmax_mhz=None, utilization=capacity,
                provenance={name: digest(attempt/name) for name in
                            ("synth_uart.json", "synth_manifest.json", "pack_uart_report.json",
                             "constraint_audit.json", "status.txt")})


def measure(folder, attempt, n_core=32, n_uart=3):
    folder, attempt = Path(folder), Path(attempt)
    if n_core < 2 or n_uart < 2:
        raise ValueError("At least two core and UART vectors are needed for rate measurements")
    implementation = implementation_evidence(folder, attempt)
    params = json.loads((folder/"params.json").read_text())
    run = folder.parent
    net = hard.load(run/"model.json")
    # Verify the selected model regenerates the synthesized core exactly.
    pipeline = params["LAT"] == params["D"]+2+int(params["head_pipeline"])
    rtl, regenerated = emit_rtl(net, pipeline=pipeline, head_pipeline=params["head_pipeline"])
    if rtl != (folder/"dlgn_top.sv").read_text() or any(params[k] != v for k, v in regenerated.items()):
        raise ValueError("Model and parameters do not regenerate the synthesized core")
    if params["hardware_clks_per_bit"] != 104 or params["clock_hz"] != 12_000_000:
        raise ValueError("Expected hardware divider 104 at 12 MHz")
    if params["input_bytes"] != (params["IN"]+7)//8 or params["reply_bytes"] != params["K"]+3:
        raise ValueError("Packet metadata differs from UART RTL")
    x = np.load(run/"x_test_bits.npy")
    n = max(n_core, n_uart)
    if n > len(x) or x.ndim != 2 or x.shape[1] != params["IN"]:
        raise ValueError("Insufficient or incorrectly shaped input vectors")
    job = Path(tempfile.mkdtemp(prefix="performance.", dir=folder))
    for name in ("dlgn_top.sv", "uart.sv", "dlgn_uart.sv", "board_top.sv"):
        shutil.copyfile(folder/name, job/name)
    shutil.copyfile(ROOT/"rtl/tb_performance.sv", job/"tb_dlgn.sv")
    definitions = {k: params[k] for k in ("IN", "K", "SW", "CW", "LAT")}
    definitions.update(NCORE=n_core, NUART=n_uart, NV=n, CPB=104, INPUT_BYTES=params["input_bytes"])
    # Compilation-unit parameters are supported by Icarus and included only in this bench.
    (job/"performance_params.svh").write_text("\n".join(f"parameter {k}={v};" for k,v in definitions.items())+"\n")
    write_vectors(net, x[:n], job, params)
    tool = shutil.which("iverilog")
    runtime = shutil.which("vvp")
    if not tool or not runtime:
        raise ValueError("Icarus iverilog and vvp are required for the cycle measurement")
    commands = [[tool, "-g2012", "-s", "tb_dlgn", "-o", "simv", "tb_dlgn.sv", "dlgn_top.sv"],
                [runtime, "simv"]]
    for name, command in zip(("build.log", "sim.log"), commands):
        result = subprocess.run(command, cwd=job, capture_output=True, text=True, timeout=120)
        (job/name).write_text(result.stdout+result.stderr)
        if result.returncode:
            raise ValueError(f"Performance simulation failed; see {job/name}")
    log = (job/"sim.log").read_text()
    core = re.findall(r"CORE vectors=(\d+) stages=(\d+) port_cycles=(\d+) capture_cycles=(\d+) ii_cycles=(\d+)", log)
    serial = re.findall(r"UART index=(\d+) start_half_cycles=(\d+) complete_half_cycles=(\d+) bytes=(\d+)", log)
    if len(core) != 1 or len(serial) != n_uart or "PASS: core and UART performance boundaries checked" not in log:
        raise ValueError("Missing performance measurement evidence")
    vectors, stages, port, capture, ii = map(int, core[0])
    rows = [tuple(map(int, row)) for row in serial]
    if vectors != n_core or stages != params["LAT"] or port != stages-1 or capture != stages or ii != 1:
        raise ValueError("Invalid measured core contract")
    if any(index != i or end <= start or size != params["reply_bytes"] for i,(index,start,end,size) in enumerate(rows)):
        raise ValueError("Invalid measured UART transaction")
    durations = [(end-start)/2 for _,start,end,_ in rows]
    intervals = [(rows[i+1][1]-rows[i][1])/2 for i in range(len(rows)-1)]
    if any(v <= 0 for v in intervals):
        raise ValueError("Invalid UART request-start intervals")
    qualified_clock = params["clock_hz"] if implementation["timing_qualified"] else None
    cycles_to_ns = lambda c: c*1e9/qualified_clock if qualified_clock else None
    return dict(
        export_directory=str(folder), implementation_directory=str(attempt), implementation=implementation,
        architecture=dict(layer_pipeline=pipeline, head_pipeline=params["head_pipeline"],
                          depth=params["D"], width=params["W"], inputs=params["IN"], classes=params["K"]),
        core=dict(register_stages=stages, verified_vectors=vectors, port_latency_cycles=port,
                  downstream_capture_cycles=capture, initiation_interval_cycles=ii,
                  port_latency_ns_at_qualified_clock=cycles_to_ns(port),
                  downstream_capture_ns_at_qualified_clock=cycles_to_ns(capture),
                  interface_capacity_predictions_per_second=qualified_clock/ii if qualified_clock else None,
                  scope="Standalone core interface capacity; UART board cannot supply one image each clock"),
        uart=dict(verified_transactions=n_uart, clocks_per_bit=104,
                  request_bytes=params["input_bytes"]+2, reply_bytes=params["reply_bytes"],
                  nominal_nonoverlap_wire_budget_cycles=(params["input_bytes"]+2+params["reply_bytes"])*10*104,
                  request_to_full_reply_cycles=durations, request_start_intervals_cycles=intervals,
                  request_to_full_reply_ms_at_qualified_clock=[cycles_to_ns(v)/1e6 for v in durations] if qualified_clock else None,
                  ideal_host_simulated_predictions_per_second=qualified_clock/(sum(intervals)/len(intervals)) if qualified_clock else None,
                  scope="RTL simulation with hardware divider, full last stop bit, immediate ideal-host next request; no USB/OS delays"),
        evidence=dict(simulation_directory=str(job), model_sha256=digest(run/"model.json"),
                      input_array_sha256=digest(run/"x_test_bits.npy"),
                      files={name:digest(job/name) for name in
                             ("tb_dlgn.sv", "performance_params.svh", "dlgn_top.sv", "uart.sv",
                              "dlgn_uart.sv", "board_top.sv", "x.hex", "exp_scores.hex", "exp_class.hex", "sim.log")},
                      iverilog=dict(path=str(Path(tool).resolve()), binary_sha256=digest(tool)),
                      vvp=dict(path=str(Path(runtime).resolve()), binary_sha256=digest(runtime))))


def check_comparison(architectures):
    """An architecture comparison holds the trained function and workload fixed."""
    if len(architectures) > 1:
        first = architectures[0]
        for other in architectures[1:]:
            for key in ("model_sha256", "input_array_sha256"):
                if first["evidence"][key] != other["evidence"][key]:
                    raise ValueError(f"Architecture comparison requires the same {key}")
            for key in ("clocks_per_bit", "request_bytes", "reply_bytes"):
                if first["uart"][key] != other["uart"][key]:
                    raise ValueError(f"Architecture comparison requires the same UART {key}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("folder", type=Path)
    ap.add_argument("implementation", type=Path)
    ap.add_argument("--comparison", nargs=2, type=Path, metavar=("EXPORT", "ATTEMPT"))
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    try:
        candidates = [(a.folder,a.implementation)] + ([tuple(a.comparison)] if a.comparison else [])
        result = dict(schema=1, architectures=[measure(*pair) for pair in candidates],
                      limitations=["Cycle simulation and archived timing, not physical throughput measurement",
                                   "Unroutable candidate has cycle counts only; qualified times/rates and Fmax are unavailable",
                                   "UART stop-bit sampling can overlap the end of the last request byte with the reply",
                                   "No energy or power reduction measured"])
        check_comparison(result["architectures"])
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as e:
        ap.exit(1, f"Performance report rejected: {e}\n")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n")
    for candidate in result["architectures"]:
        print(candidate["export_directory"], candidate["implementation"]["outcome"],
              f"port={candidate['core']['port_latency_cycles']} cycles; II=1;",
              f"UART cycles={candidate['uart']['request_to_full_reply_cycles']}")


if __name__ == "__main__":
    main()
