"""Export a trained run to RTL + testbench + vectors.

  python scripts/export.py runs/digits_w1000 --n 450            # combinational
  python scripts/export.py runs/digits_w1000 --n 450 --pipeline # 1 reg / layer
Outputs go to <run>/rtl_comb or <run>/rtl_pipe.
"""
import argparse
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dlgn import hard                       # noqa: E402
from dlgn.export_verilog import export      # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run")
    ap.add_argument("--n", type=int, default=0, help="test vectors (0 = all)")
    ap.add_argument("--pipeline", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    net = hard.load(os.path.join(a.run, "model.json"))
    x = np.load(os.path.join(a.run, "x_test_bits.npy"))
    if a.n:
        x = x[:a.n]
    out = a.out or os.path.join(a.run, "rtl_pipe" if a.pipeline else "rtl_comb")
    p = export(net, x, out, pipeline=a.pipeline)
    with open(os.path.join(out, "params.json"), "w") as f:
        json.dump(p, f, indent=2)
    print(f"wrote {out}/ (dlgn_top.sv, tb_dlgn.sv, {len(x)} vectors) "
          f"latency={p['LAT']} cycles, score width={p['SW']} bits")


if __name__ == "__main__":
    main()
