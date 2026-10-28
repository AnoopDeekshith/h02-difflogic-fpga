#!/usr/bin/env bash
# Run the self-checking testbench in an exported RTL folder.
#   sim/run_sim.sh runs/digits_w1000/rtl_comb            # auto-pick simulator
#   SIM=xsim sim/run_sim.sh runs/.../rtl_comb             # Vivado simulator
#   DUMP=1   sim/run_sim.sh runs/.../rtl_comb             # also write dlgn.vcd
# Exits non-zero unless the testbench prints PASS.
set -euo pipefail
DIR=$(cd "$1" && pwd)
cd "$DIR"

if [[ -z "${SIM:-}" ]]; then
  if command -v verilator >/dev/null || command -v verilator-cli >/dev/null; then SIM=verilator
  elif command -v iverilog >/dev/null; then SIM=iverilog
  elif command -v xvlog >/dev/null; then SIM=xsim
  else echo "No simulator found (install verilator: pip install verilator)"; exit 2; fi
fi
DEF=""; [[ -n "${DUMP:-}" ]] && DEF="DUMP"

case "$SIM" in
  verilator)
    V=$(command -v verilator || command -v verilator-cli)
    "$V" --binary --timing -Wno-fatal -Wno-WIDTHTRUNC -Wno-WIDTHEXPAND \
         ${DEF:+-D$DEF --trace} --top-module tb_dlgn -j 0 \
         tb_dlgn.sv dlgn_top.sv -o simv --Mdir obj_dir > build.log 2>&1 \
      || { tail -30 build.log; exit 1; }
    ./obj_dir/simv | tee sim.log ;;
  iverilog)
    iverilog -g2012 ${DEF:+-D$DEF} -o simv tb_dlgn.sv dlgn_top.sv
    vvp simv | tee sim.log ;;
  xsim)
    xvlog -sv ${DEF:+-d $DEF} tb_dlgn.sv dlgn_top.sv > build.log
    xelab tb_dlgn -s tb_snap > elab.log
    xsim tb_snap -R | tee sim.log ;;
esac
grep -q "^PASS" sim.log
