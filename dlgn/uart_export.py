"""Export a board wrapper and serial testbench around the existing DLGN core."""
import json
from pathlib import Path
import shutil

from .export_verilog import export

ROOT = Path(__file__).resolve().parents[1]


def export_uart(net, x_bits, outdir, pipeline=False, sim_clks_per_bit=104, head_pipeline=False):
    if sim_clks_per_bit < 8:
        raise ValueError("UART simulation requires at least 8 clocks per bit")
    # Protocol v1 carries one byte per score and one byte for the class index.
    if net["n_classes"] > 256 or net["width"] // net["n_classes"] > 255:
        raise ValueError("UART protocol requires class indices and scores to fit in a byte")
    if not len(x_bits):
        raise ValueError("At least one input vector is required")
    p = export(net, x_bits, outdir, pipeline=pipeline, head_pipeline=head_pipeline)
    out = Path(outdir)
    for name in ("uart.sv", "dlgn_uart.sv"):
        shutil.copyfile(ROOT / "rtl" / name, out / name)
    shutil.copyfile(ROOT / "rtl/tb_uart.sv", out / "tb_dlgn.sv")
    shutil.copyfile(ROOT / "synth/icebreaker_uart.pcf", out / "icebreaker_uart.pcf")
    # Specialize the board top to this model; actual hardware always uses CPB=104.
    (out / "board_top.sv").write_text(
        "module board_top(input wire clk, button_n, uart_rx_pin, "
        "output wire uart_tx_pin);\n"
        f"  icebreaker_top #(.IN({p['IN']}), .K({p['K']}), "
        f".SW({p['SW']}), .CW({p['CW']})) board "
        "(.clk(clk), .button_n(button_n), .uart_rx_pin(uart_rx_pin), "
        ".uart_tx_pin(uart_tx_pin));\nendmodule\n"
    )
    (out / "uart_params.svh").write_text(
        f"localparam IN={p['IN']}, K={p['K']}, SW={p['SW']}, CW={p['CW']}, "
        f"N={len(x_bits)}, CPB={sim_clks_per_bit};\n"
    )
    p.update(clock_hz=12_000_000, baud_requested=115_200,
             hardware_clks_per_bit=104, sim_clks_per_bit=sim_clks_per_bit,
             input_bytes=(p["IN"] + 7) // 8, reply_bytes=p["K"] + 3)
    (out / "params.json").write_text(json.dumps(p, indent=2) + "\n")
    return p
