#!/usr/bin/env bash
# Check synthesis -> place/route -> timing -> bitstream on a small counter.
# Usage: bash synth/check_ice40_flow.sh [output-directory]
# This does not program hardware or measure the DLGN's timing.
set -euo pipefail

ROOT=$(cd "$(dirname "$0")/.." && pwd)
OUT=${1:-"$ROOT/runs/toolchain_smoke"}
for tool in yosys nextpnr-ice40 icepack; do
    command -v "$tool" >/dev/null || {
        echo "Missing $tool. Install Yosys, nextpnr-ice40, and IceStorm." >&2
        exit 2
    }
done
mkdir -p "$OUT"
OUT=$(cd "$OUT" && pwd)
cp "$ROOT/synth/timing_smoke.sv" "$OUT/timing_smoke.sv"
cp "$ROOT/synth/icebreaker_smoke.pcf" "$OUT/icebreaker_smoke.pcf"
cd "$OUT"

{ yosys -V; nextpnr-ice40 --version; } > tools.txt 2>&1
yosys -Q -q -l synth.log -p \
    'read_verilog -sv timing_smoke.sv; synth_ice40 -top timing_smoke -json synth.json'
if ! nextpnr-ice40 --up5k --package sg48 --freq 12 --seed 1 \
    --json synth.json --pcf icebreaker_smoke.pcf \
    --asc routed.asc --report timing.json > nextpnr.log 2>&1; then
    tail -40 nextpnr.log >&2
    exit 1
fi
awk '/Max frequency for clock/ {last = $0} END {print last}' nextpnr.log
icepack routed.asc timing_smoke.bin
test -s timing_smoke.bin
echo "PASS: iCE40 tool flow completed at a 12 MHz target. Results: $OUT"
echo "This checks the counter only; DLGN placement/routing and timing remain pending."
