"""Read and cross-check an archived 12 MHz UP5K UART routing result.

This is a read-only report of a saved implementation, not a clock sweep or
physical frequency measurement. No installed FPGA executable is required.
"""
import argparse
from collections import defaultdict
import json
import math
from pathlib import Path

from build_artifacts import digest

INPUT_FILES = {"synth_uart.json", "synth_manifest.json", "icebreaker_uart.pcf",
               "icebreaker_uart.sdc", "tools.txt"}
OUTPUT_FILES = {"routed_uart.asc", "routed_uart.json", "timing_uart.json", "pnr_uart.log"}


def summarize(folder):
    folder = Path(folder)
    if (folder/"status.txt").read_text().strip() != "validated_route_passed":
        raise ValueError("Attempt does not have validated_route_passed status")
    saved = json.loads((folder/"validated_result.json").read_text())
    for group, names in (("input_files", INPUT_FILES), ("files", OUTPUT_FILES)):
        if set(saved[group]) != names:
            raise ValueError(f"Incomplete archived {group} fingerprints")
        for name in sorted(names):
            if digest(folder/name) != saved[group][name]:
                raise ValueError(f"Archived file hash mismatch: {name}")
    manifest = json.loads((folder/"synth_manifest.json").read_text())
    if digest(folder/"synth_uart.json") != manifest["files"]["synth_uart.json"]:
        raise ValueError("Archived synthesis manifest does not match routed input")
    # Params live in the export directory, so an old route must not inherit a
    # subsequent export's clock or latency. The archived manifest binds them.
    params_path = folder.parent/"params.json"
    if digest(params_path) != manifest["files"]["params.json"]:
        raise ValueError("Parent params.json differs from the archived synthesis")
    params = json.loads(params_path.read_text())
    if params["clock_hz"] != 12_000_000:
        raise ValueError("Expected the 12 MHz hardware clock")
    report = json.loads((folder/"timing_uart.json").read_text())
    netlist = json.loads((folder/"routed_uart.json").read_text())["modules"]["top"]
    settings = netlist["settings"]
    if (settings.get("arch.type"), settings.get("arch.package")) != ("up5k", "sg48"):
        raise ValueError("Expected iCE40UP5K-SG48")
    if not all(int(settings.get(k, "0").strip(), 2) == 1 for k in ("pack", "place", "route")):
        raise ValueError("Missing pack/place/route completion")
    if not netlist["cells"] or any("NEXTPNR_BEL" not in c["attributes"] for c in netlist["cells"].values()):
        raise ValueError("Expected nonempty placed-cell evidence")
    clocks = report["fmax"]
    if len(clocks) != 1:
        raise ValueError("Expected exactly one clock")
    name, clock = next(iter(clocks.items()))
    fmax, target = float(clock["achieved"]), float(clock["constraint"])
    if not all(math.isfinite(v) and v > 0 for v in (fmax, target)) or abs(target-12) > .001 or fmax < target:
        raise ValueError("Invalid clock estimate or unmet 12 MHz target")
    if saved["clock"] != clock or saved["target"] != "iCE40UP5K-SG48":
        raise ValueError("Saved validation disagrees with raw clock/target")
    utilization = report["utilization"]
    if utilization != saved["utilization"] or "ICESTORM_LC" not in utilization:
        raise ValueError("Missing or inconsistent utilization")
    if any(not 0 <= v["used"] <= v["available"] for v in utilization.values()):
        raise ValueError("Device capacity exceeded or invalid utilization")
    if not (folder/"routed_uart.asc").stat().st_size:
        raise ValueError("Empty routed ASC")
    log = (folder/"pnr_uart.log").read_text()
    if "ERROR:" in log or "Routing complete." not in log or "Program finished normally." not in log:
        raise ValueError("Routing log does not establish success")
    # Use only the same-clock rising-edge register path for this clock estimate.
    # Asynchronous input/output paths are retained separately, not folded into it.
    edge = f"posedge {name}"
    paths = report["critical_paths"]
    sync = [p for p in paths if p["from"] == edge and p["to"] == edge]
    if len(sync) != 1 or not sync[0]["path"]:
        raise ValueError("Expected one nonempty synchronous critical path")
    segments = sync[0]["path"]
    breakdown = defaultdict(float)
    for s in segments:
        delay = float(s["delay"])
        if not math.isfinite(delay) or delay < 0:
            raise ValueError("Invalid synchronous segment delay")
        breakdown[s["type"]] += delay
    if set(breakdown) != {"clk-to-q", "routing", "logic", "setup"}:
        raise ValueError("Unexpected synchronous path delay categories")
    path_ns = sum(breakdown.values())
    period_ns, budget_ns = 1000/fmax, 1000/target
    if not math.isclose(path_ns, period_ns, abs_tol=.001, rel_tol=0):
        raise ValueError("Synchronous path sum does not agree with Fmax")
    cross = [{"from": p["from"], "to": p["to"],
              "delay_ns": sum(float(s["delay"]) for s in p["path"])}
             for p in paths if p is not sync[0]]
    if any(not math.isfinite(p["delay_ns"]) or p["delay_ns"] < 0 for p in cross):
        raise ValueError("Invalid cross-domain path delay")
    return dict(
        schema=1, scope="Archived tool-estimated single-clock timing; no physical clock measurement",
        implementation_directory=str(folder), target=saved["target"], clock_name=name,
        operating_clock_hz=params["clock_hz"], constraint_mhz=target,
        estimated_fmax_mhz=fmax, target_met=True,
        estimated_min_period_ns=period_ns, constraint_period_ns=budget_ns,
        period_margin_ns=budget_ns-period_ns,
        synchronous_path=dict(delay_ns=path_ns, delay_by_type_ns=dict(breakdown),
                              start=segments[0]["from"], end=segments[-1]["to"]),
        cross_domain_paths=cross, utilization=utilization,
        provenance=dict(validation_sha256=digest(folder/"validated_result.json"),
                        params_sha256=digest(params_path), input_files=saved["input_files"],
                        output_files=saved["files"], nextpnr=saved.get("nextpnr")),
        limitations=["Fmax describes this routed implementation at a 12 MHz constraint; no frequency sweep",
                     "Period margin is arithmetic from the clock estimate, not a separate slack report",
                     "Cross-domain delays do not certify asynchronous I/O or synchronizer MTBF",
                     "No board operation, power reduction or energy reduction measured"]
                    + (["This older validation record has no executable fingerprint; tool identity is unavailable"]
                       if not saved.get("nextpnr") else []))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("folder", type=Path)
    ap.add_argument("--out", type=Path, help="Write the checked summary JSON")
    a = ap.parse_args()
    try:
        result = summarize(a.folder)
    except (OSError, ValueError, KeyError, TypeError) as e:
        ap.exit(1, f"Timing report rejected: {e}\n")
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        a.out.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(f"PASS: {result['estimated_fmax_mhz']:.6f} MHz estimated Fmax; "
          f"12 MHz target met; {result['synchronous_path']['delay_ns']:.3f} ns synchronous path")
    print("This is a saved tool estimate, not a measured board frequency.")


if __name__ == "__main__":
    main()
