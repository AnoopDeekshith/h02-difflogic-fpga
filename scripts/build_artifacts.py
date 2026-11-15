"""Fingerprint synthesis inputs and validate fresh routed artifacts."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SYNTH_FILES = ("dlgn_top.sv", "uart.sv", "dlgn_uart.sv", "board_top.sv", "params.json",
               "synth_uart.json", "synth_uart_stat.txt")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def record_synth(folder):
    result = dict(schema=1, files={name: digest(folder/name) for name in SYNTH_FILES})
    tool = shutil.which("yosys") or shutil.which("yowasp-yosys")
    if tool:
        result["tool"] = dict(path=str(Path(tool).resolve()), binary_sha256=digest(tool),
                              version=subprocess.check_output([tool, "-V"], text=True).strip())
    (folder/"synth_manifest.json").write_text(json.dumps(result, indent=2)+"\n")


def check_synth(folder):
    manifest = json.loads((folder/"synth_manifest.json").read_text())
    if set(manifest["files"]) != set(SYNTH_FILES):
        raise ValueError("Incomplete synthesis manifest; rerun synthesis")
    for name, expected in manifest["files"].items():
        if digest(folder/name) != expected:
            raise ValueError(f"Stale synthesis artifact {name}; export/synthesize again")
    for name in ("uart.sv", "dlgn_uart.sv"):
        if digest(folder/name) != digest(ROOT/"rtl"/name):
            raise ValueError(f"Export contains outdated {name}; export/synthesize again")
    return manifest


def validate_route(folder):
    manifest = json.loads((folder/"synth_manifest.json").read_text())
    if digest(folder/"synth_uart.json") != manifest["files"]["synth_uart.json"]:
        raise ValueError("Archived routed input does not match the synthesis manifest")
    report = json.loads((folder/"timing_uart.json").read_text())
    mapped = json.loads((folder/"routed_uart.json").read_text())["modules"]["top"]
    def enabled(key):
        value = mapped["settings"].get(key, "0")
        return isinstance(value, str) and value.strip() and int(value.strip(), 2) == 1
    if not all(enabled(k) for k in ("pack", "place", "route")):
        raise ValueError("Missing pack/place/route completion flags")
    if mapped["settings"].get("arch.type") != "up5k" or mapped["settings"].get("arch.package") != "sg48":
        raise ValueError("Routed artifact targets the wrong FPGA/package")
    clocks = report.get("fmax", {})
    if len(clocks) != 1:
        raise ValueError("Expected one clock in the routed timing report")
    for clock in clocks.values():
        achieved, target = float(clock["achieved"]), float(clock["constraint"])
        if not all(math.isfinite(v) for v in (achieved, target)) or abs(target-12) > .001 or achieved < target:
            raise ValueError(f"12 MHz timing not met: {clock}")
    utilization = report.get("utilization", {})
    if "ICESTORM_LC" not in utilization or any(v["used"] > v["available"] for v in utilization.values()):
        raise ValueError("Missing capacity evidence or exceeded device capacity")
    if any("NEXTPNR_BEL" not in c["attributes"] for c in mapped["cells"].values()):
        raise ValueError("Routed netlist contains unplaced cells")
    asc = folder/"routed_uart.asc"
    if not asc.is_file() or asc.stat().st_size == 0:
        raise ValueError("Missing routed ASC configuration")
    log = (folder/"pnr_uart.log").read_text()
    if "ERROR:" in log or "Routing complete." not in log or "Program finished normally." not in log:
        raise ValueError("Log does not establish successful routing")
    return dict(scope="Tool-estimated single-clock routing/timing; not physical board or power validation",
                target="iCE40UP5K-SG48", clock=next(iter(clocks.values())),
                utilization=utilization,
                input_files={name: digest(folder/name) for name in
                             ("synth_uart.json", "synth_manifest.json", "icebreaker_uart.pcf",
                              "icebreaker_uart.sdc", "tools.txt")},
                nextpnr=dict(path=str(Path(shutil.which("nextpnr-ice40")).resolve()),
                             binary_sha256=digest(shutil.which("nextpnr-ice40"))),
                files={name: digest(folder/name) for name in
                       ("routed_uart.asc", "routed_uart.json", "timing_uart.json", "pnr_uart.log")})


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("action", choices=["record-synth", "check-synth", "validate-route"])
    ap.add_argument("folder", type=Path)
    a = ap.parse_args()
    try:
        if a.action == "record-synth":
            record_synth(a.folder)
        elif a.action == "check-synth":
            check_synth(a.folder)
        else:
            result = validate_route(a.folder)
            (a.folder/"validated_result.json").write_text(json.dumps(result, indent=2)+"\n")
    except (ValueError, KeyError, OSError) as e:
        ap.exit(1, f"Artifact validation failed: {e}\n")
    print(f"PASS: {a.action}")


if __name__ == "__main__":
    main()
