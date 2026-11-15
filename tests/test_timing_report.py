"""Independent fault injection for archived timing reports; no FPGA tools needed."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_artifacts import digest
from report_timing import INPUT_FILES, OUTPUT_FILES, summarize


def write_json(path, value):
    path.write_text(json.dumps(value))


def refresh_hashes(folder):
    """Bind intentionally changed fixture files, preserving other validation fields."""
    saved_path = folder / "validated_result.json"
    saved = json.loads(saved_path.read_text())
    for field, files in (("input_files", INPUT_FILES), ("files", OUTPUT_FILES)):
        saved[field] = {name: digest(folder / name) for name in files}
    write_json(saved_path, saved)


@pytest.fixture
def archive(tmp_path):
    folder = tmp_path / "implementation.fixture"
    folder.mkdir()
    write_json(tmp_path / "params.json", {"clock_hz": 12_000_000, "LAT": 3})
    write_json(folder / "synth_uart.json", {"design": "fixture"})
    write_json(folder / "synth_manifest.json", {"files": {
        "params.json": digest(tmp_path / "params.json"),
        "synth_uart.json": digest(folder / "synth_uart.json"),
    }})
    write_json(folder / "routed_uart.json", {"modules": {"top": {
        "settings": {"arch.type": "up5k", "arch.package": "sg48",
                     "pack": "1", "place": "1", "route": "1"},
        "cells": {"registered_cell": {"attributes": {"NEXTPNR_BEL": "X1/Y1/lc0"}}},
    }}})
    point = {"cell": "fixture_input", "port": "Q", "loc": [1, 1]}
    segment = lambda kind, delay: {"type": kind, "delay": delay,
                                   "from": point, "to": point}
    clock = {"achieved": 20.0, "constraint": 12.0}
    utilization = {"ICESTORM_LC": {"used": 100, "available": 5280}}
    report = {
        "fmax": {"clk": clock}, "utilization": utilization,
        "critical_paths": [
            # Deliberately first, and longer: this must not become synchronous Fmax.
            {"from": "<async>", "to": "posedge clk",
             "path": [segment("routing", 400.0)]},
            {"from": "posedge clk", "to": "posedge clk", "path": [
                segment("clk-to-q", 1.0), segment("routing", 30.0),
                segment("logic", 18.0), segment("setup", 1.0)]},
        ],
    }
    write_json(folder / "timing_uart.json", report)
    for name in ("routed_uart.asc", "icebreaker_uart.pcf", "icebreaker_uart.sdc", "tools.txt"):
        (folder / name).write_text("fixture\n")
    (folder / "pnr_uart.log").write_text(
        "Max frequency: 18 MHz\nRouting complete.\nProgram finished normally.\n")
    (folder / "status.txt").write_text("validated_route_passed\n")
    write_json(folder / "validated_result.json", {
        "target": "iCE40UP5K-SG48", "clock": clock,
        "utilization": utilization, "nextpnr": {"binary_sha256": "archived-tool"},
    })
    refresh_hashes(folder)
    return folder


def test_archived_clock_uses_json_and_same_clock_path_without_live_tools(archive, monkeypatch):
    monkeypatch.setenv("PATH", "")
    before = {p: p.read_bytes() for p in archive.iterdir()}
    result = summarize(archive)
    assert result["estimated_fmax_mhz"] == 20.0
    assert result["estimated_min_period_ns"] == 50.0
    assert result["synchronous_path"]["delay_ns"] == 50.0
    assert result["synchronous_path"]["delay_by_type_ns"]["routing"] == 30.0
    assert result["period_margin_ns"] == pytest.approx(1000 / 12 - 50)
    assert result["cross_domain_paths"][0]["delay_ns"] == 400.0
    assert result["provenance"]["nextpnr"]["binary_sha256"] == "archived-tool"
    assert before == {p: p.read_bytes() for p in archive.iterdir()}


@pytest.mark.parametrize("filename", ["timing_uart.json", "routed_uart.json", "icebreaker_uart.sdc"])
def test_changed_archived_file_rejected(archive, filename):
    path = archive / filename
    path.write_text(path.read_text() + " ")
    with pytest.raises(ValueError, match="hash mismatch"):
        summarize(archive)


def test_old_route_cannot_inherit_changed_export_params(archive):
    write_json(archive.parent / "params.json", {"clock_hz": 12_000_000, "LAT": 7})
    with pytest.raises(ValueError, match="Parent params"):
        summarize(archive)


def test_failed_attempt_with_old_output_files_is_rejected(archive):
    (archive / "status.txt").write_text("failed (exit 1)\n")
    with pytest.raises(ValueError, match="status"):
        summarize(archive)


def test_saved_validation_clock_must_match_raw_report(archive):
    path = archive / "validated_result.json"
    saved = json.loads(path.read_text())
    saved["clock"]["achieved"] = 21
    write_json(path, saved)
    with pytest.raises(ValueError, match="disagrees"):
        summarize(archive)


def test_legacy_validation_keeps_missing_tool_identity_explicit(archive, monkeypatch):
    monkeypatch.setenv("PATH", "")
    path = archive / "validated_result.json"
    saved = json.loads(path.read_text())
    del saved["nextpnr"]
    write_json(path, saved)
    before = path.read_bytes()
    result = summarize(archive)
    assert result["estimated_fmax_mhz"] == 20
    assert result["provenance"]["nextpnr"] is None
    assert any("no executable fingerprint" in note for note in result["limitations"])
    assert path.read_bytes() == before
    (archive / "icebreaker_uart.sdc").write_text("changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        summarize(archive)


@pytest.mark.parametrize("fault", [
    "missing_sync", "duplicate_sync", "period_mismatch", "nan_segment",
    "negative_segment", "nan_fmax", "unmet_target", "multiple_clocks",
    "nan_cross_domain", "missing_delay_category",
])
def test_internally_bound_but_invalid_timing_rejected(archive, fault):
    path = archive / "timing_uart.json"
    report = json.loads(path.read_text())
    sync = report["critical_paths"][1]
    if fault == "missing_sync":
        report["critical_paths"] = report["critical_paths"][:1]
    elif fault == "duplicate_sync":
        report["critical_paths"].append(sync)
    elif fault == "period_mismatch":
        sync["path"][1]["delay"] += 1
    elif fault == "nan_segment":
        sync["path"][1]["delay"] = float("nan")
    elif fault == "negative_segment":
        sync["path"][1]["delay"] = -1
    elif fault == "nan_fmax":
        report["fmax"]["clk"]["achieved"] = float("nan")
    elif fault == "unmet_target":
        report["fmax"]["clk"]["achieved"] = 7
    elif fault == "multiple_clocks":
        report["fmax"]["other_clock"] = {"achieved": 30, "constraint": 12}
    elif fault == "nan_cross_domain":
        report["critical_paths"][0]["path"][0]["delay"] = float("nan")
    elif fault == "missing_delay_category":
        sync["path"][0]["type"] = "logic"
    write_json(path, report)
    refresh_hashes(archive)
    with pytest.raises(ValueError):
        summarize(archive)
