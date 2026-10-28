"""RTL vs NumPy golden model on a random network that uses all 16 gates,
both combinational and pipelined. Needs a simulator (pip install verilator).
Run: python -m pytest tests -q"""
import os
import shutil
import subprocess
import sys
import tempfile

import numpy as np

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
from dlgn.export_verilog import export   # noqa: E402


def random_net(in_dim=48, width=60, depth=3, k=6, seed=1):
    rng = np.random.default_rng(seed)
    layers, prev = [], in_dim
    for _ in range(depth):
        layers.append(dict(ia=rng.integers(0, prev, width).tolist(),
                           ib=rng.integers(0, prev, width).tolist(),
                           gates=(np.arange(width) % 16).tolist()))
        prev = width
    return dict(in_dim=in_dim, width=width, depth=depth, n_classes=k,
                tau=1.0, layers=layers)


def _have_sim():
    return any(shutil.which(s) for s in ("verilator", "verilator-cli", "iverilog", "xvlog"))


def _run(pipeline):
    net = random_net()
    x = np.random.default_rng(2).random((300, net["in_dim"])) > 0.5
    d = tempfile.mkdtemp(prefix="dlgn_")
    export(net, x, d, pipeline=pipeline)
    r = subprocess.run(["bash", os.path.join(ROOT, "sim", "run_sim.sh"), d],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    assert "PASS" in r.stdout


def test_comb():
    if _have_sim():
        _run(False)


def test_pipe():
    if _have_sim():
        _run(True)
