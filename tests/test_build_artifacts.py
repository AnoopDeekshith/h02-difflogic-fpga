"""Reject stale or internally inconsistent implementation evidence."""
import json
from pathlib import Path
import shutil
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"scripts"))
from build_artifacts import digest, validate_route, record_synth, check_synth, SYNTH_FILES


def write_json(path, data):
    path.write_text(json.dumps(data))


@pytest.fixture
def successful(tmp_path):
    # A minimal internally consistent artifact bundle for validator fault injection.
    write_json(tmp_path/"synth_uart.json", {"original": True})
    write_json(tmp_path/"synth_manifest.json", {"files": {"synth_uart.json": digest(tmp_path/"synth_uart.json")}})
    report = dict(fmax={"clk": {"achieved":19.3, "constraint":12}},
                  utilization={"ICESTORM_LC": {"used":4160, "available":5280}})
    write_json(tmp_path/"timing_uart.json", report)
    mapped = dict(settings={"pack":"1", "place":"1", "route":"1",
                            "arch.type":"up5k", "arch.package":"sg48"},
                  cells={"cell": {"attributes": {"NEXTPNR_BEL":"X1/Y1/lc0"}}})
    write_json(tmp_path/"routed_uart.json", {"modules": {"top":mapped}})
    for name in ("routed_uart.asc", "icebreaker_uart.pcf", "icebreaker_uart.sdc", "tools.txt"):
        (tmp_path/name).write_text("test fixture\n")
    (tmp_path/"pnr_uart.log").write_text("Routing complete.\nProgram finished normally.\n")
    return tmp_path


def test_consistent_artifacts(successful):
    if not shutil.which("nextpnr-ice40"):
        pytest.skip("nextpnr required for tool fingerprint")
    assert validate_route(successful)["clock"]["achieved"] == 19.3


@pytest.mark.parametrize("fault", ["slow", "nan", "no_clock", "overcapacity", "unrouted", "wrong_target", "stale_input", "unplaced", "empty_asc"])
def test_invalid_evidence_rejected(successful, fault):
    report = json.loads((successful/"timing_uart.json").read_text())
    netlist = json.loads((successful/"routed_uart.json").read_text())
    if fault == "slow": report["fmax"]["clk"]["achieved"] = 7
    if fault == "nan": report["fmax"]["clk"]["achieved"] = float("nan")
    if fault == "no_clock": report["fmax"] = {}
    if fault == "overcapacity": report["utilization"]["ICESTORM_LC"]["used"] = 6000
    if fault == "unrouted": netlist["modules"]["top"]["settings"]["route"] = "0"
    if fault == "wrong_target": netlist["modules"]["top"]["settings"]["arch.type"] = "hx8k"
    if fault == "stale_input": (successful/"synth_uart.json").write_text("changed")
    if fault == "unplaced": netlist["modules"]["top"]["cells"]["cell"]["attributes"] = {}
    if fault == "empty_asc": (successful/"routed_uart.asc").write_text("")
    write_json(successful/"timing_uart.json", report)
    write_json(successful/"routed_uart.json", netlist)
    with pytest.raises(ValueError):
        validate_route(successful)


def test_stale_synthesis_rejected(tmp_path):
    for name in SYNTH_FILES:
        (tmp_path/name).write_text("fixture")
    for name in ("uart.sv", "dlgn_uart.sv"):
        shutil.copyfile(ROOT/"rtl"/name, tmp_path/name)
    record_synth(tmp_path)
    check_synth(tmp_path)
    (tmp_path/"dlgn_top.sv").write_text("modified core")
    with pytest.raises(ValueError, match="Stale synthesis"):
        check_synth(tmp_path)
