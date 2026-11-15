"""Export UART board interface and its self-checking serial simulation."""
import argparse
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dlgn import hard
from dlgn.uart_export import export_uart


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run", type=Path)
    ap.add_argument("--pipeline", action="store_true")
    ap.add_argument("--head-pipeline", action="store_true", help="register class scores and balance argmax")
    ap.add_argument("--n", type=int, default=0, help="vectors, 0 = all")
    ap.add_argument("--sim-clks-per-bit", type=int, default=104,
                    help="simulation only; 8 is faster, hardware stays at 104")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    net = hard.load(a.run / "model.json")
    x = np.load(a.run / "x_test_bits.npy")
    if a.n < 0:
        ap.error("--n must be nonnegative")
    if a.n:
        x = x[:a.n]
    out = a.out or a.run / ("uart_pipe" if a.pipeline else "uart_comb")
    if a.head_pipeline and a.out is None:
        out = out.with_name(out.name + "_head")
    p = export_uart(net, x, out, a.pipeline, a.sim_clks_per_bit, a.head_pipeline)
    print(f"wrote {out}: {len(x)} UART test images, "
          f"{p['input_bytes']} image bytes, {p['reply_bytes']} reply bytes; "
          f"core latency {p['LAT']} cycles")


if __name__ == "__main__":
    main()
