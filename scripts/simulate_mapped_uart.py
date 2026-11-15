"""Functional check of synthesized iCE40 cells (not timing/glitch simulation)."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from build_artifacts import check_synth

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("export", type=Path)
    ap.add_argument("--n", type=int, default=12)
    a = ap.parse_args()
    folder = a.export.resolve()
    check_synth(folder)
    p = json.loads((folder/"params.json").read_text())
    vectors = (folder/"x.hex").read_text().splitlines()
    n = min(a.n, len(vectors))
    if n < 1:
        ap.error("--n must be positive")
    out = Path(tempfile.mkdtemp(prefix="mapped_sim.", dir=folder))
    for name in ("x.hex", "exp_scores.hex", "exp_class.hex"):
        lines = (folder/name).read_text().splitlines()[:n]
        (out/name).write_text("\n".join(lines)+"\n")
    shutil.copyfile(folder/"synth_uart.json", out/"synth_uart.json")
    datdir = subprocess.check_output(["yosys-config", "--datdir"], text=True).strip()
    shutil.copyfile(Path(datdir)/"ice40/cells_sim.v", out/"cells_sim.v")
    subprocess.run(["yosys", "-Q", "-q", "-p",
                    "read_json synth_uart.json; write_verilog -noattr dlgn_top.sv"], cwd=out, check=True)
    mapped = out/"dlgn_top.sv"
    mapped.write_text('`include "cells_sim.v"\n' + mapped.read_text())
    (out/"tb_dlgn.sv").write_text('`define MAPPED_UART\n' + (ROOT/"rtl/tb_uart.sv").read_text())
    (out/"uart_params.svh").write_text(
        f"localparam IN={p['IN']}, K={p['K']}, SW={p['SW']}, CW={p['CW']}, N={n}, CPB=104;\n")
    print(f"Mapped functional simulation: {out}", flush=True)
    subprocess.run(["bash", str(ROOT/"sim/run_sim.sh"), str(out)], check=True)


if __name__ == "__main__":
    main()
