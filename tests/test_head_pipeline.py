"""Independent head-pipeline regression: exhaustive inputs, odd class counts, ties."""
import itertools
import os
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dlgn import hard
from dlgn.export_verilog import export


def network(classes, tied):
    rng = np.random.default_rng(20261114 + classes)
    width = classes * 5
    previous = 10
    layers = []
    for _ in range(3):
        layers.append(dict(
            ia=(np.arange(width) % previous).tolist() if tied else rng.integers(previous, size=width).tolist(),
            ib=rng.integers(previous, size=width).tolist(),
            gates=[3] * width if tied else (np.arange(width) % 16).tolist(),
        ))
        previous = width
    if tied and classes > 1:
        # Only classes 1 and last are nonconstant, with identical score functions.
        # This guarantees nonzero winning ties across the odd tree's subtrees.
        layers[-1]["gates"] = [0] * width
        for group in (1, classes - 1):
            for bit in range(5):
                layers[-1]["ia"][group * 5 + bit] = bit
                layers[-1]["gates"][group * 5 + bit] = 3
    return dict(in_dim=10, width=width, depth=3, n_classes=classes, tau=1, layers=layers)


@pytest.mark.parametrize("classes", [1, 3, 5, 10])
@pytest.mark.parametrize("pipeline", [False, True])
@pytest.mark.parametrize("tied", [False, True])
def test_head_pipeline_exhaustive(tmp_path, classes, pipeline, tied):
    if not shutil.which("iverilog"):
        pytest.skip("Icarus required for exhaustive head-pipeline regression")
    net = network(classes, tied)
    inputs = np.array(list(itertools.product([False, True], repeat=10)), dtype=bool)
    if tied and classes > 1:
        scores = hard.scores(net, inputs)
        assert np.array_equal(scores[:, 1], scores[:, -1])
        assert set(scores.argmax(1)) == {0, 1}  # all-zero tie and nonzero winning tie
    params = export(net, inputs, tmp_path, pipeline=pipeline, head_pipeline=True)
    assert params["LAT"] == (6 if pipeline else 3)
    result = subprocess.run(
        ["bash", str(ROOT / "sim/run_sim.sh"), str(tmp_path)],
        env={**os.environ, "SIM": "iverilog"},
        capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-4000:]
    assert "1024/1024 vectors bit-exact" in result.stdout
