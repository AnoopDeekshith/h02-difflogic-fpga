"""Check pin coverage, clock period, and synchronizer connectivity before P&R."""
import argparse
import json
from pathlib import Path
import re
import shlex

PINS = {"clk": "35", "button_n": "10", "uart_rx_pin": "6", "uart_tx_pin": "9"}


def check(netlist, pcf, sdc):
    m = netlist["modules"]["board_top"]
    ports, cells = m["ports"], m["cells"]
    if set(ports) != set(PINS) or any(len(p["bits"]) != 1 for p in ports.values()):
        raise ValueError("Expected exactly four scalar board ports")
    for name, port in ports.items():
        expected = "output" if name == "uart_tx_pin" else "input"
        if port["direction"] != expected:
            raise ValueError(f"Unexpected direction for {name}")
    assigned = {}
    for line in pcf.splitlines():
        words = shlex.split(line, comments=True)
        if not words:
            continue
        if len(words) != 3 or words[0] != "set_io":
            raise ValueError("Expected explicit set_io <port> <pin> assignments")
        if words[1] in assigned:
            raise ValueError(f"Repeated pin constraint for {words[1]}")
        assigned[words[1]] = words[2]
    if assigned != PINS:
        raise ValueError(f"Missing or incorrect board pins: {assigned}")
    commands = [line.split("#", 1)[0].strip() for line in sdc.splitlines()]
    commands = [line for line in commands if line]
    if len(commands) != 1:
        raise ValueError("Expected exactly one clock constraint and no timing exceptions")
    match = re.fullmatch(r"create_clock -name clk12 -period ([0-9.]+) \[get_ports clk\]", commands[0])
    if not match or abs(float(match[1]) - 1000 / 12) > 1e-6:
        raise ValueError("Expected the 12 MHz clock on port clk")

    clk = ports["clk"]["bits"]
    rx = ports["uart_rx_pin"]["bits"]
    registers = [c for c in cells.values() if c["type"].startswith("SB_DFF")]
    if not registers or any(c["connections"]["C"] != clk for c in registers):
        raise ValueError("All mapped registers must use the single board clock")
    # Resolve actual cells through Q bits, rather than relying on cell names.
    def driver(bit):
        found = [(name, c) for name, c in cells.items()
                 if c.get("port_directions", {}).get("Q") == "output"
                 and c["connections"].get("Q") == [bit]]
        if len(found) != 1:
            raise ValueError(f"Expected one register driver for bit {bit}")
        return found[0]

    def consumers(bit):
        return [(name, port) for name, c in cells.items()
                for port, bits in c["connections"].items()
                if c["port_directions"].get(port) == "input" and bit in bits]

    meta = m["netnames"]["board.adapter.receiver.rx_meta"]["bits"][0]
    sync = m["netnames"]["board.adapter.receiver.rx_sync"]["bits"][0]
    meta_name, meta_cell = driver(meta)
    sync_name, sync_cell = driver(sync)
    if not (meta_cell["type"].startswith("SB_DFF") and sync_cell["type"].startswith("SB_DFF")
            and meta_cell["connections"]["D"] == rx
            and sync_cell["connections"]["D"] == [meta]
            and meta_cell["connections"]["C"] == sync_cell["connections"]["C"] == clk
            and consumers(meta) == [(sync_name, "D")]
            and consumers(rx[0]) == [(meta_name, "D")]):
        raise ValueError("RX must enter only the first stage of a two-register synchronizer")

    # Yosys maps the reset's set-to-one shift chain to inverted SB_DFFR states.
    resets = [(name, c) for name, c in cells.items() if c["type"] == "SB_DFFR"]
    first = [(name, c) for name, c in resets if c["connections"]["D"] == ["1"]]
    if len(resets) != 2 or len(first) != 1:
        raise ValueError("Expected the two asynchronous-reset release registers")
    first_name, first_cell = first[0]
    second_name, second_cell = next((n, c) for n, c in resets if n != first_name)
    reset_net = first_cell["connections"]["R"]
    invert = [c for c in cells.values() if c["type"] == "SB_LUT4"
              and c["connections"].get("O") == reset_net
              and c["connections"].get("I3") == ports["button_n"]["bits"]
              and int(c["parameters"]["LUT_INIT"], 2) == 0x00ff]
    if not (len(invert) == 1
            and first_cell["connections"]["C"] == second_cell["connections"]["C"] == clk
            and second_cell["connections"]["R"] == reset_net
            and second_cell["connections"]["D"] == first_cell["connections"]["Q"]
            and consumers(first_cell["connections"]["Q"][0]) == [(second_name, "D")]):
        raise ValueError("Reset must assert asynchronously and release through two registers")
    return dict(target="iCE40UP5K-SG48", clock_mhz=12, period_ns=1000/12,
                pins=assigned, single_clock_registers=len(registers),
                rx_registers=[meta_name, sync_name],
                reset_registers=[first_name, second_name], timing_exceptions=[],
                scope="Synthesized connectivity only; not physical CDC or timing signoff")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("netlist", type=Path)
    ap.add_argument("--pcf", type=Path, required=True)
    ap.add_argument("--sdc", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--pack-report", type=Path, help="also check packed resource capacity")
    a = ap.parse_args()
    try:
        result = check(json.loads(a.netlist.read_text()), a.pcf.read_text(), a.sdc.read_text())
    except (ValueError, KeyError) as e:
        ap.exit(1, f"Constraint check failed: {e}\n")
    exceeded = []
    if a.pack_report:
        utilization = json.loads(a.pack_report.read_text())["utilization"]
        result["packed_utilization"] = utilization
        exceeded = [f"{name}: {v['used']}/{v['available']}"
                    for name, v in utilization.items() if v["used"] > v["available"]]
        result["within_resource_capacity"] = not exceeded
    a.out.write_text(json.dumps(result, indent=2) + "\n")
    print("PASS: four board pins, 12 MHz clock, and two-stage RX/reset connectivity")
    if exceeded:
        ap.exit(3, "Capacity exceeded (constraints passed): " + "; ".join(exceeded) + "\n")
    if a.pack_report:
        lc = result["packed_utilization"]["ICESTORM_LC"]
        print(f"Packed logic cells: {lc['used']}/{lc['available']}; routability still unproven")


if __name__ == "__main__":
    main()
