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
"$ROOT/.venv/bin/python" "$ROOT/scripts/build_artifacts.py" check-synth "$DIR"
"$ROOT/.venv/bin/python" "$ROOT/scripts/check_board_constraints.py" "$DIR/synth_uart.json" \
    --pcf "$ROOT/synth/icebreaker_uart.pcf" --sdc "$ROOT/synth/icebreaker_uart.sdc" \
    --out "$DIR/constraint_audit.json"
cp "$ROOT/synth/icebreaker_uart.pcf" "$DIR/icebreaker_uart.pcf"
cp "$ROOT/synth/icebreaker_uart.sdc" "$DIR/icebreaker_uart.sdc"
cd "$DIR"
# Every attempt has an empty output directory, so old successful files cannot
# turn a failed new attempt into apparent evidence of success.
JOB=$(mktemp -d "$DIR/implementation.XXXXXX")
cp synth_uart.json synth_manifest.json icebreaker_uart.pcf icebreaker_uart.sdc "$JOB/"
printf '%s\n' "$JOB" > latest_attempt.txt
cd "$JOB"
printf '%s\n' running > status.txt
trap 'code=$?; if [[ $code -ne 0 ]]; then printf "failed (exit %s)\n" "$code" > "$JOB/status.txt"; fi' EXIT
{ command -v nextpnr-ice40; nextpnr-ice40 --version; } > tools.txt 2>&1
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
    printf '%s\n' constraints_and_packing_passed > status.txt
else
    "$ROOT/.venv/bin/python" "$ROOT/scripts/build_artifacts.py" validate-route "$JOB"
    awk '/Max frequency for clock/ {last=$0} END {print last}' "$LOG"
    printf '%s\n' "$JOB" > "$DIR/latest_success.txt"
    printf '%s\n' validated_route_passed > status.txt
    echo "PASS: validated placement/routing. Results: $JOB"
fi
