"""Catch incorrect clock/pins and CDC wiring using a real synthesized wrapper."""
from copy import deepcopy
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
from check_board_constraints import check
from dlgn.uart_export import export_uart


@pytest.fixture(scope="module")
def synthesized(tmp_path_factory):
    if not shutil.which("yosys"):
        pytest.skip("Native Yosys required for mapped synchronizer regression")
    out = tmp_path_factory.mktemp("constraints")
    net = dict(in_dim=16, width=20, depth=1, n_classes=2, tau=1,
               layers=[dict(ia=(np.arange(20) % 16).tolist(),
                            ib=((np.arange(20)+1) % 16).tolist(),
                            gates=(np.arange(20) % 16).tolist())])
    export_uart(net, np.zeros((1, 16), dtype=bool), out)
    subprocess.run(["bash", str(ROOT / "synth/synth_uart_ice40.sh"), str(out)],
                   check=True, capture_output=True, text=True, timeout=120)
    return json.loads((out / "synth_uart.json").read_text())


def constraints():
    return ((ROOT / "synth/icebreaker_uart.pcf").read_text(),
            (ROOT / "synth/icebreaker_uart.sdc").read_text())


def test_valid_constraints(synthesized):
    pcf, sdc = constraints()
    assert check(synthesized, pcf, sdc)["clock_mhz"] == 12


def test_missing_pin_rejected(synthesized):
    pcf, sdc = constraints()
    with pytest.raises(ValueError, match="board pins"):
        check(synthesized, pcf.replace("set_io uart_rx_pin 6", ""), sdc)


def test_wrong_clock_and_exceptions_rejected(synthesized):
    pcf, sdc = constraints()
    with pytest.raises(ValueError, match="12 MHz"):
        check(synthesized, pcf, sdc.replace("83.333333333333", "10"))
    with pytest.raises(ValueError, match="no timing exceptions"):
        check(synthesized, pcf, sdc + "set_false_path -from [get_ports uart_rx_pin]\n")


def test_rx_bypass_rejected(synthesized):
    modified = deepcopy(synthesized)
    pcf, sdc = constraints()
    m = modified["modules"]["board_top"]
    sync_bit = m["netnames"]["board.adapter.receiver.rx_sync"]["bits"]
    sync = next(c for c in m["cells"].values() if c["connections"].get("Q") == sync_bit)
    sync["connections"]["D"] = m["ports"]["uart_rx_pin"]["bits"]
    with pytest.raises(ValueError, match="two-register synchronizer"):
        check(modified, pcf, sdc)


def test_unexpected_register_clock_rejected(synthesized):
    modified = deepcopy(synthesized)
    pcf, sdc = constraints()
    m = modified["modules"]["board_top"]
    register = next(c for c in m["cells"].values() if c["type"].startswith("SB_DFF"))
    register["connections"]["C"] = m["ports"]["button_n"]["bits"]
    with pytest.raises(ValueError, match="single board clock"):
        check(modified, pcf, sdc)


def test_reset_bypass_rejected(synthesized):
    modified = deepcopy(synthesized)
    pcf, sdc = constraints()
    cells = modified["modules"]["board_top"]["cells"]
    del cells[next(name for name, c in cells.items() if c["type"] == "SB_DFFR")]
    with pytest.raises(ValueError, match="reset release registers"):
        check(modified, pcf, sdc)
