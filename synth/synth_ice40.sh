#!/usr/bin/env bash
# Synthesize an exported RTL folder for iCE40 (iCEBreaker, UP5K) with Yosys.
#   synth/synth_ice40.sh runs/digits_w1000/rtl_comb
# Writes synth_ice40.log, synth_ice40.json (netlist for nextpnr) and prints LUT/FF counts.
set -euo pipefail
DIR=$(cd "$1" && pwd)
cd "$DIR"

Y=$(command -v yosys || command -v yowasp-yosys) \
  || { echo "No yosys found (pip install yowasp-yosys)"; exit 2; }

"$Y" -q -l synth_ice40.log \
     -p "read_verilog -sv dlgn_top.sv; synth_ice40 -top dlgn_top -json synth_ice40.json; tee -o synth_ice40_stat.txt stat"

LUT=$(awk '$2 == "SB_LUT4" {print $1; exit}' synth_ice40_stat.txt)
FF=$(awk '$2 ~ /^SB_DFF/ {s += $1} END {print s + 0}' synth_ice40_stat.txt)
CARRY=$(awk '$2 == "SB_CARRY" {print $1; exit}' synth_ice40_stat.txt)
echo "iCE40: LUT4 ${LUT:-0}  FF ${FF}  CARRY ${CARRY:-0}  (UP5K has 5280 LUT4)"
