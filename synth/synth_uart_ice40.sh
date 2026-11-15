#!/usr/bin/env bash
# Synthesize a scripts/export_uart.py directory, including its board interface.
# Does not place/route, check timing, or program hardware.
set -euo pipefail
if [[ $# != 1 ]]; then
    echo "Usage: bash synth/synth_uart_ice40.sh <UART-export-directory>" >&2
    exit 2
fi
DIR=$(cd "$1" && pwd)
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$DIR"
Y=$(command -v yosys || command -v yowasp-yosys) || {
    echo "No Yosys found" >&2; exit 2;
}
"$Y" -q -l synth_uart.log -p \
    'read_verilog -sv dlgn_top.sv uart.sv dlgn_uart.sv board_top.sv; synth_ice40 -top board_top -json synth_uart.json; tee -o synth_uart_stat.txt stat'
"$ROOT/.venv/bin/python" "$ROOT/scripts/build_artifacts.py" record-synth "$DIR"
LUT=$(awk '$2 == "SB_LUT4" {print $1; exit}' synth_uart_stat.txt)
FF=$(awk '$2 ~ /^SB_DFF/ {s += $1} END {print s + 0}' synth_uart_stat.txt)
CARRY=$(awk '$2 == "SB_CARRY" {print $1; exit}' synth_uart_stat.txt)
echo "UART board top: LUT4 ${LUT:-0}  FF $FF  CARRY ${CARRY:-0}"
