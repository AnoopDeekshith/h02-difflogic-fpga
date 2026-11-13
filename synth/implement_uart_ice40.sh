#!/usr/bin/env bash
# Constrain and implement a UART export; --pack-only validates step 2.7 only.
# Requires synth_uart.json from synth/synth_uart_ice40.sh. Does not program a board.
set -euo pipefail
if [[ $# -lt 1 || $# -gt 2 || ( $# == 2 && "$2" != "--pack-only" ) ]]; then
    echo "Usage: bash synth/implement_uart_ice40.sh <UART-export-directory> [--pack-only]" >&2
    exit 2
fi
ROOT=$(cd "$(dirname "$0")/.." && pwd)
DIR=$(cd "$1" && pwd)
command -v nextpnr-ice40 >/dev/null || { echo "Missing nextpnr-ice40" >&2; exit 2; }
"$ROOT/.venv/bin/python" "$ROOT/scripts/check_board_constraints.py" "$DIR/synth_uart.json" \
    --pcf "$ROOT/synth/icebreaker_uart.pcf" --sdc "$ROOT/synth/icebreaker_uart.sdc" \
    --out "$DIR/constraint_audit.json"
cp "$ROOT/synth/icebreaker_uart.pcf" "$DIR/icebreaker_uart.pcf"
cp "$ROOT/synth/icebreaker_uart.sdc" "$DIR/icebreaker_uart.sdc"
cd "$DIR"
OPTIONS=()
if [[ ${2:-} == "--pack-only" ]]; then
    OPTIONS=(--pack-only --write packed_uart.json --report pack_uart_report.json)
    LOG=pack_uart.log
else
    OPTIONS=(--asc routed_uart.asc --write routed_uart.json --report timing_uart.json --detailed-timing-report)
    LOG=pnr_uart.log
fi
if ! nextpnr-ice40 --up5k --package sg48 --freq 12 --seed 1 \
    --json synth_uart.json --pcf icebreaker_uart.pcf --sdc icebreaker_uart.sdc \
    "${OPTIONS[@]}" > "$LOG" 2>&1; then
    tail -40 "$LOG" >&2
    exit 1
fi
if [[ ${2:-} == "--pack-only" ]]; then
    "$ROOT/.venv/bin/python" "$ROOT/scripts/check_board_constraints.py" synth_uart.json \
        --pcf icebreaker_uart.pcf --sdc icebreaker_uart.sdc \
        --pack-report pack_uart_report.json --out constraint_audit.json
    echo "PASS: constraint/packing checks; placement, routing, and timing remain pending."
else
    awk '/Max frequency for clock/ {last=$0} END {print last}' "$LOG"
    echo "PASS: placement/routing completed; inspect timing_uart.json and pnr_uart.log."
fi
