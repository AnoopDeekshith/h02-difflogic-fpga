"""Independent step 3.3 checks of the shipped capture bench and its ledger.

The VCD decoder here is separate from the production observability inspector.
It checks complete transactions; it does not calculate activity or power.
"""
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from dlgn import hard  # noqa: E402
from dlgn.export_verilog import emit_rtl, write_vectors  # noqa: E402
from capture_baseline_waveform import validate_events, write_parameters  # noqa: E402


def decode_selected_vcd(path, suffixes):
    """Return end-of-timestamp values for selected hierarchical signal suffixes."""
    scope = []
    signals = {}
    selected = {}
    current = {}
    timestamp = 0
    snapshots = {}
    body = False
    with Path(path).open() as source:
        for line in source:
            words = line.split()
            if not words:
                continue
            if not body:
                if words[0] == "$scope":
                    scope.append(words[2])
                elif words[0] == "$upscope":
                    scope.pop()
                elif words[0] == "$var":
                    name = ".".join(scope + [words[4]])
                    for suffix in suffixes:
                        if name == suffix or name.endswith("." + suffix):
                            assert suffix not in signals, f"Ambiguous suffix {suffix}"
                            signals[suffix] = (words[3], int(words[2]))
                elif words[0] == "$enddefinitions":
                    assert set(signals) == set(suffixes), set(suffixes) - set(signals)
                    for name, (identifier, _) in signals.items():
                        selected.setdefault(identifier, []).append(name)
                    body = True
                continue
            token = words[0]
            if token.startswith("#"):
                snapshots[timestamp] = current.copy()
                following = int(token[1:])
                assert following >= timestamp
                timestamp = following
            elif token.startswith(("b", "B")) and len(words) == 2:
                value, identifier = token[1:], words[1]
                for name in selected.get(identifier, []):
                    current[name] = None if any(c in value.lower() for c in "xz") else int(value, 2)
            elif token[0] in "01xXzZ":
                value, identifier = token[0], token[1:]
                for name in selected.get(identifier, []):
                    current[name] = int(value) if value in "01" else None
    assert body
    snapshots[timestamp] = current.copy()
    return signals, snapshots


def verify_trace(folder, net, x, params, half_period_ps=41667):
    """Independently decode every recorded input/output and marker boundary."""
    folder = Path(folder)
    n = len(x)
    names = ["dut.clk", "dut.rst", "dut.in_valid", "dut.out_valid", "dut.x",
             "dut.l0", "dut.class_out", "dut.scores", "input_index", "output_index",
             "input_count", "output_count", "cycle_index", "capture_done"]
    declarations, snapshots = decode_selected_vcd(folder / "dlgn.vcd", names)
    assert declarations["dut.x"][1] == params["IN"]
    assert declarations["dut.scores"][1] == params["K"] * params["SW"]
    with (folder / "events.csv").open() as source:
        events = list(csv.DictReader(source))
    inputs = [e for e in events if e["kind"] == "input"]
    outputs = [e for e in events if e["kind"] == "output"]
    done = [e for e in events if e["kind"] == "done"]
    assert len(inputs) == len(outputs) == n and len(done) == 1
    scores = hard.scores(net, x)
    period = 2 * half_period_ps
    for index, (inp, out) in enumerate(zip(inputs, outputs)):
        assert int(inp["index"]) == int(out["index"]) == index
        capture_time = (7 + 2 * index) * half_period_ps
        check_time = capture_time + (params["LAT"] - 1) * period + 1
        assert int(inp["time_ps"]) == capture_time
        assert int(out["time_ps"]) == check_time
        assert int(inp["cycle"]) == 4 + index
        assert int(out["cycle"]) == 4 + index + params["LAT"] - 1
        expected_input = sum(int(bit) << bit_index for bit_index, bit in enumerate(x[index]))
        expected_scores = sum(int(value) << (params["SW"] * k)
                              for k, value in enumerate(scores[index]))
        observed_input = snapshots[capture_time]
        assert observed_input["dut.rst"] == 0
        assert observed_input["dut.clk"] == observed_input["dut.in_valid"] == 1
        assert observed_input["dut.x"] == observed_input["dut.l0"] == expected_input
        assert observed_input["input_index"] == index
        assert observed_input["input_count"] == index + 1
        observed_output = snapshots[check_time]
        assert observed_output["dut.out_valid"] == 1
        assert observed_output["dut.scores"] == expected_scores
        assert observed_output["dut.class_out"] == int(scores[index].argmax())
        assert observed_output["output_index"] == index
        assert observed_output["output_count"] == index + 1
    last_output = int(outputs[-1]["time_ps"])
    end = int(done[0]["time_ps"])
    assert end - last_output == 5 * half_period_ps - 1
    assert max(snapshots) == end + 1
    final = snapshots[end]
    assert final["capture_done"] == 1
    assert final["input_count"] == final["output_count"] == n
    assert final["dut.in_valid"] == final["dut.out_valid"] == 0
    assert final["dut.x"] == sum(int(bit) << bit_index for bit_index, bit in enumerate(x[-1]))
    # Check that reset was asserted through three complete initial cycles.
    assert snapshots[5 * half_period_ps]["dut.rst"] == 1
    assert snapshots[6 * half_period_ps]["dut.rst"] == 0
    return dict(n_images=n, first_input_ps=int(inputs[0]["time_ps"]),
                last_output_check_ps=last_output, capture_done_ps=end,
                final_timestamp_ps=max(snapshots),
                independent_input_score_class_and_marker_checks=True)


@pytest.mark.parametrize("pipeline,head", [(False, False), (False, True),
                                          (True, False), (True, True)])
def test_capture_bench_records_ordered_transactions(tmp_path, pipeline, head):
    if not shutil.which("iverilog") or not shutil.which("vvp"):
        pytest.skip("Icarus required for baseline capture verification")
    rng = np.random.default_rng(19)
    layers = []
    previous = 4
    for _ in range(2):
        layers.append(dict(ia=rng.integers(previous, size=24).tolist(),
                           ib=rng.integers(previous, size=24).tolist(),
                           gates=np.tile([6, 8, 14, 12, 10, 0], 4).tolist()))
        previous = 24
    net = dict(in_dim=4, n_classes=4, layers=layers)
    x = ((np.arange(16)[:, None] >> np.arange(4)) & 1).astype(bool)
    rtl, params = emit_rtl(net, pipeline=pipeline, head_pipeline=head)
    (tmp_path / "dlgn_top.sv").write_text(rtl)
    write_vectors(net, x, tmp_path, params)
    write_parameters(tmp_path, params, len(x))
    shutil.copyfile(ROOT / "rtl/tb_activity_capture.sv", tmp_path / "tb_activity_capture.sv")
    for command in (["iverilog", "-g2012", "-s", "tb_capture", "-o", "simv",
                     "tb_activity_capture.sv", "dlgn_top.sv"], ["vvp", "simv"]):
        result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS: 16/16 baseline vectors bit-exact (scores + class)" in result.stdout
    verify_trace(tmp_path, net, x, params)
    assert validate_events(tmp_path / "events.csv", len(x), params)["input_count"] == 16


def test_repeated_zero_input_and_score_ties_are_complete_transactions(tmp_path):
    if not shutil.which("iverilog") or not shutil.which("vvp"):
        pytest.skip("Icarus required for baseline capture verification")
    net = dict(in_dim=2, n_classes=2,
               layers=[dict(ia=[0, 0, 1, 1], ib=[0, 1, 0, 1], gates=[0, 0, 0, 0])])
    x = np.zeros((5, 2), dtype=bool)
    rtl, params = emit_rtl(net, head_pipeline=True)
    (tmp_path / "dlgn_top.sv").write_text(rtl)
    write_vectors(net, x, tmp_path, params)
    write_parameters(tmp_path, params, len(x))
    shutil.copyfile(ROOT / "rtl/tb_activity_capture.sv", tmp_path / "tb_activity_capture.sv")
    for command in (["iverilog", "-g2012", "-s", "tb_capture", "-o", "simv",
                     "tb_activity_capture.sv", "dlgn_top.sv"], ["vvp", "simv"]):
        result = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
    verify_trace(tmp_path, net, x, params)
    assert "PASS: 5/5 baseline vectors bit-exact (scores + class)" in result.stdout


def _ledger():
    half, n, latency = 41667, 3, 3
    rows = []
    for index in range(n):
        cycle = 4 + index
        timestamp = (7 + 2 * index) * half
        rows.append(dict(kind="input", index=index, time_ps=timestamp, cycle=cycle))
        rows.append(dict(kind="output", index=index,
                         time_ps=timestamp + (latency - 1) * 2 * half + 1,
                         cycle=cycle + latency - 1))
    rows.sort(key=lambda row: row["time_ps"])
    rows.append(dict(kind="done", index=-1, time_ps=rows[-1]["time_ps"]+5*half-1,
                     cycle=4+n-1+latency-1+2))
    return rows


@pytest.mark.parametrize("fault", ["missing", "duplicate", "cadence", "latency", "early_done"])
def test_event_ledger_rejects_broken_workload(tmp_path, fault):
    rows = _ledger()
    if fault == "missing":
        rows.pop(0)
    elif fault == "duplicate":
        rows[1]["index"] = 0
    elif fault == "cadence":
        rows[1]["time_ps"] += 1
    elif fault == "latency":
        for row in rows:
            if row["kind"] == "output":
                row["time_ps"] += 2
    elif fault == "early_done":
        rows[-1]["time_ps"] = 0
    path = tmp_path / "events.csv"
    with path.open("w") as dest:
        writer = csv.DictWriter(dest, fieldnames=["kind", "index", "time_ps", "cycle"])
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError):
        validate_events(path, 3, dict(LAT=3))
