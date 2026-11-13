"""Exercise the physical serial pins with real reference scores, not a stub core."""
from pathlib import Path
import os
import shutil
import subprocess
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dlgn.uart_export import export_uart


def make_net(tied=False):
    rng = np.random.default_rng(17)
    layers = []
    prev = 13  # exercise padding in the final byte
    for _ in range(3):
        layers.append(dict(ia=rng.integers(prev, size=40).tolist(),
                           ib=rng.integers(prev, size=40).tolist(),
                           gates=(np.arange(40) % 16).tolist()))
        prev = 40
    if tied:
        layers[-1]["gates"] = [0] * 40
    return dict(in_dim=13, width=40, depth=3, n_classes=4, tau=1, layers=layers)


@pytest.mark.parametrize("pipeline,tied", [(False, False), (True, False), (False, True)])
def test_uart_end_to_end(tmp_path, pipeline, tied):
    if not shutil.which("iverilog"):
        pytest.skip("Icarus required for UART regression")
    net = make_net(tied)
    x = np.random.default_rng(18).integers(2, size=(6, 13)).astype(bool)
    x[0] = False
    x[1] = True
    export_uart(net, x, tmp_path, pipeline=pipeline)  # actual 104-cycle UART divisor
    r = subprocess.run(["bash", str(ROOT / "sim/run_sim.sh"), str(tmp_path)],
                       env={**os.environ, "SIM": "iverilog"},
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout[-4000:] + r.stderr[-4000:]
    assert "6/6 UART images bit-exact" in r.stdout


def test_uart_rejects_unrepresentable_scores(tmp_path):
    net = make_net()
    net["width"] = 1024
    with pytest.raises(ValueError, match="fit in a byte"):
        export_uart(net, np.zeros((1, 13)), tmp_path)
