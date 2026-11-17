"""Independent recording checks using small, reproducible RTL exports.

These verify the existing DUMP path, not physical timing or activity totals.
"""
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dlgn.export_verilog import export  # noqa: E402
from scripts.check_waveform_recording import inspect_vcd  # noqa: E402


@pytest.mark.parametrize("pipeline,head", [(False, False), (False, True),
                                          (True, False), (True, True)])
def test_dump_is_passive_and_records_every_layer(tmp_path, pipeline, head):
    if not shutil.which("iverilog") or not shutil.which("vvp"):
        pytest.skip("Icarus is required for this recording check")
    rng = np.random.default_rng(123)
    width, depth, classes = 40, 3, 4
    layers = []
    previous = 4
    for _ in range(depth):
        layers.append(dict(ia=rng.integers(previous, size=width).tolist(),
                           ib=rng.integers(previous, size=width).tolist(),
                           gates=np.tile([6, 8, 14, 12, 10], 8).tolist()))
        previous = width
    net = dict(in_dim=4, n_classes=classes, layers=layers)
    x = ((np.arange(16)[:, None] >> np.arange(4)) & 1).astype(bool)
    source_hashes = []
    for recording in (False, True):
        folder = tmp_path / ("on" if recording else "off")
        export(net, x, folder, pipeline=pipeline, head_pipeline=head)
        env = os.environ.copy()
        env["SIM"] = "iverilog"
        env.pop("DUMP", None)
        if recording:
            env["DUMP"] = "1"
        result = subprocess.run(["bash", str(ROOT / "sim/run_sim.sh"), str(folder)],
                                env=env, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "PASS: 16/16 vectors bit-exact (scores + class)" in result.stdout
        source_hashes.append({name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                              for name in ("dlgn_top.sv", "tb_dlgn.sv", "x.hex",
                                           "exp_scores.hex", "exp_class.hex")})
        trace = folder / "dlgn.vcd"
        assert trace.exists() == recording
        if recording:
            text = trace.read_text()
            header, body = text.split("$enddefinitions $end", 1)
            assert "$timescale" in header
            assert "$scope module dut $end" in header
            declarations = dict((name, identifier) for identifier, name in
                                re.findall(r"\$var \S+ \d+ (\S+) (\S+).*?\$end", header))
            required = {"clk", "rst", "in_valid", "out_valid", "x", "scores", "class_out"}
            required |= {f"l{i}" for i in range(depth + 1)}
            required |= {f"l{i}_c" for i in range(1, depth + 1)}
            assert required <= declarations.keys()
            times = [int(t) for t in re.findall(r"^#(\d+)$", body, re.MULTILINE)]
            assert len(times) > 16 and times[-1] > times[0]
            for name in ("clk", "rst", "in_valid", "out_valid"):
                identifier = re.escape(declarations[name])
                assert re.search(rf"^0{identifier}$", body, re.MULTILINE)
                assert re.search(rf"^1{identifier}$", body, re.MULTILINE)
    assert source_hashes[0] == source_hashes[1]


def _minimal_trace():
    # l1/l1_c intentionally share an identifier; unknown initialization is legal.
    return """$timescale 1ps $end
$scope module tb_dlgn $end
$scope module dut $end
$var wire 1 c clk $end
$var wire 1 r rst $end
$var wire 1 i in_valid $end
$var wire 1 o out_valid $end
$var wire 2 X x [1:0] $end
$var wire 2 s scores [1:0] $end
$var wire 1 C class_out $end
$var wire 2 A l0 [1:0] $end
$var wire 2 L l1 [1:0] $end
$var wire 2 L l1_c [1:0] $end
$upscope $end
$upscope $end
$enddefinitions $end
#0
$dumpvars
xc
xr
xi
xo
bx X
bx s
xC
bx A
bx L
$end
#5
0c
0r
0i
0o
b00 X
b01 s
0C
b00 A
b01 L
#10
1c
1r
1i
1o
b01 X
"""


PARAMS = dict(IN=2, K=2, SW=1, CW=1, W=2, D=1)


def test_inspector_accepts_aliases_and_unknown_initialization(tmp_path):
    path = tmp_path / "trace.vcd"
    path.write_text(_minimal_trace())
    result = inspect_vcd(path, PARAMS)
    assert result["final_timestamp"] == 10
    assert result["required_signals"]["l1"]["identifier"] == "L"
    assert result["required_signals"]["l1_c"]["identifier"] == "L"


@pytest.mark.parametrize("old,new,reason", [
    ("$var wire 2 L l1_c [1:0] $end\n", "", "Missing DUT signals"),
    ("$var wire 2 s scores", "$var wire 3 s scores", "Wrong VCD width"),
    ("b01 L\n", "bx L\n", "No known value"),
    ("1c\n", "", "No high/low"),
    ("b01 X\n", "", "No input data changes"),
    ("#5\n", "#11\n", "time moved backwards"),
    ("$timescale 1ps $end\n", "", "lacks complete"),
    ("$enddefinitions $end\n", "", "lacks complete"),
    ("#10\n", "#0\n", "time moved backwards"),
])
def test_inspector_rejects_incomplete_recording(tmp_path, old, new, reason):
    path = tmp_path / "bad.vcd"
    path.write_text(_minimal_trace().replace(old, new))
    with pytest.raises(ValueError, match=reason):
        inspect_vcd(path, PARAMS)
