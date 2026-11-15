"""Independent edge-to-edge latency/II checks, including invalid input bubbles."""
from pathlib import Path
import copy
import re
import shutil
import subprocess
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dlgn.export_verilog import export
from dlgn.uart_export import export_uart
sys.path.insert(0, str(ROOT / "scripts"))
from report_performance import check_comparison


def test_architecture_comparison_requires_same_function_workload_and_packets():
    candidate = {"evidence": {"model_sha256": "same-model", "input_array_sha256": "same-inputs"},
                 "uart": {"clocks_per_bit": 104, "request_bytes": 26, "reply_bytes": 13}}
    check_comparison([candidate, copy.deepcopy(candidate)])
    for group, key in (("evidence", "model_sha256"), ("evidence", "input_array_sha256"),
                       ("uart", "clocks_per_bit"), ("uart", "request_bytes"),
                       ("uart", "reply_bytes")):
        changed = copy.deepcopy(candidate)
        changed[group][key] = "different" if group == "evidence" else changed[group][key]+1
        with pytest.raises(ValueError, match="Architecture comparison requires"):
            check_comparison([candidate, changed])


@pytest.mark.parametrize("pipeline", [False, True])
@pytest.mark.parametrize("head_pipeline", [False, True])
def test_registered_port_and_downstream_capture_latencies(tmp_path, pipeline, head_pipeline):
    if not shutil.which("iverilog") or not shutil.which("vvp"):
        pytest.skip("Icarus required for independent cycle-contract check")
    rng = np.random.default_rng(2102026)
    layers, prev = [], 13
    for _ in range(4):
        layers.append(dict(ia=rng.integers(prev, size=40).tolist(),
                           ib=rng.integers(prev, size=40).tolist(),
                           gates=(np.arange(40) % 16).tolist()))
        prev = 40
    net = dict(in_dim=13, width=40, depth=4, n_classes=5, tau=1, layers=layers)
    inputs = rng.integers(2, size=(48, 13)).astype(bool)
    params = export(net, inputs, tmp_path, pipeline=pipeline, head_pipeline=head_pipeline)
    # Expected latency is derived from physical register stages, not params['LAT'].
    stages = 2 + (4 if pipeline else 0) + int(head_pipeline)
    assert params["LAT"] == stages
    tb = r"""`timescale 1ns/1ps
module tb_cycle;
  localparam N=48, STAGES=__STAGES__;
  reg clk=0, rst=1, in_valid=0;
  reg [12:0] x=0;
  wire out_valid;
  wire [2:0] class_out;
  wire [19:0] scores;
  reg [12:0] xmem [0:N-1];
  reg [19:0] smem [0:N-1];
  reg [2:0] cmem [0:N-1];
  integer accepted_at [0:N-1];
  integer presented_at [0:N-1];
  integer cycle=0, nin=0, nout=0, captured=0, adjacent=0;
  dlgn_top dut(.*);
  always #5 clk=~clk;
  // A receiver register observes the previous NBA result at the next edge.
  always @(posedge clk) begin
    cycle=cycle+1;
    if (!rst && out_valid) begin
      if (captured>=N) $fatal(1,"Extra downstream result");
      if (cycle-accepted_at[captured] != STAGES)
        $fatal(1,"Downstream capture latency mismatch");
      if (scores !== smem[captured] || class_out !== cmem[captured])
        $fatal(1,"Downstream payload mismatch");
      captured=captured+1;
    end
  end
  // Sample registered output after NBA, separately from downstream capture.
  always @(posedge clk) begin
    #1;
    if (!rst) begin
      if (in_valid) begin
        if (nin>=N) $fatal(1,"Extra input");
        accepted_at[nin]=cycle;
        nin=nin+1;
      end
      if (out_valid) begin
        if (nout>=nin) $fatal(1,"Result without accepted input");
        if (cycle-accepted_at[nout] != STAGES-1)
          $fatal(1,"Registered output availability latency mismatch");
        if (scores !== smem[nout] || class_out !== cmem[nout])
          $fatal(1,"Registered output payload mismatch");
        presented_at[nout]=cycle;
        if (nout>0) begin
          if (presented_at[nout]-presented_at[nout-1]
              != accepted_at[nout]-accepted_at[nout-1])
            $fatal(1,"Output spacing does not preserve input bubbles");
          if (accepted_at[nout]-accepted_at[nout-1]==1) adjacent=adjacent+1;
        end
        nout=nout+1;
      end
    end
  end
  initial begin
    $readmemh("x.hex",xmem);
    $readmemh("exp_scores.hex",smem);
    $readmemh("exp_class.hex",cmem);
    repeat(3) @(negedge clk);
    rst=0;
    for(integer i=0;i<N;i=i+1) begin
      @(negedge clk);
      in_valid=1; x=xmem[i];
      // Change invalid data too, so bubbles cannot masquerade as repeated inputs.
      if (i%7==6) begin
        @(negedge clk); in_valid=0; x=~xmem[i];
        @(negedge clk); in_valid=0; x=13'h123;
      end
    end
    @(negedge clk); in_valid=0;
    wait(nout==N && captured==N);
    repeat(STAGES+2) @(negedge clk);
    if(nin!=N || nout!=N || captured!=N || adjacent<30)
      $fatal(1,"Incomplete stream or II=1 evidence");
    $display("PASS cycle contract: availability=%0d capture=%0d II=1 vectors=%0d",
             STAGES-1,STAGES,N);
    $finish;
  end
  initial begin #100000; $fatal(1,"Timeout"); end
endmodule
""".replace("__STAGES__", str(stages))
    (tmp_path / "tb_cycle.sv").write_text(tb)
    build = subprocess.run(["iverilog", "-g2012", "-s", "tb_cycle", "-o", "cycle_sim",
                            "tb_cycle.sv", "dlgn_top.sv"], cwd=tmp_path,
                           capture_output=True, text=True, timeout=60)
    assert build.returncode == 0, build.stdout + build.stderr
    sim = subprocess.run(["vvp", "cycle_sim"], cwd=tmp_path,
                         capture_output=True, text=True, timeout=60)
    assert sim.returncode == 0, sim.stdout + sim.stderr
    assert f"availability={stages-1} capture={stages} II=1 vectors=48" in sim.stdout


def test_uart_serial_work_sum_is_not_wall_latency_lower_bound(tmp_path):
    """RX can respond during the final request stop-bit tail on separate wires."""
    if not shutil.which("iverilog") or not shutil.which("vvp"):
        pytest.skip("Icarus required for independent UART-boundary check")
    rng = np.random.default_rng(2102027)
    net = dict(in_dim=13, width=40, depth=1, n_classes=5, tau=1,
               layers=[dict(ia=rng.integers(13, size=40).tolist(),
                            ib=rng.integers(13, size=40).tolist(),
                            gates=(np.arange(40) % 16).tolist())])
    export_uart(net, rng.integers(2, size=(3, 13)).astype(bool), tmp_path,
                head_pipeline=True)
    tb = r"""`timescale 1ns/1ps
module tb_uart_boundary;
  localparam CPB=104, N=3, REQUEST_BYTES=4, REPLY_BYTES=8;
  reg clk=0,rst=1,rx=1;
  wire tx;
  reg [12:0] xs[0:N-1];
  reg [19:0] ss[0:N-1];
  reg [2:0] cs[0:N-1];
  integer packet=0;
  time req_start, reply_end;
  realtime first_wall=0;
  dlgn_uart #(.IN(13),.K(5),.SW(4),.CW(3),.CLKS_PER_BIT(CPB)) dut
    (.clk(clk),.rst(rst),.uart_rx_pin(rx),.uart_tx_pin(tx));
  always #5 clk=~clk;
  task send_byte(input [7:0] value);
    rx=0; repeat(CPB) @(negedge clk);
    for(integer b=0;b<8;b=b+1) begin
      rx=value[b]; repeat(CPB) @(negedge clk);
    end
    rx=1; repeat(CPB) @(negedge clk);
  endtask
  task receive_byte(output [7:0] value);
    @(negedge tx);
    #(CPB*10+CPB*5);
    for(integer b=0;b<8;b=b+1) begin value[b]=tx; #(CPB*10); end
    if(tx!==1) $fatal(1,"Bad stop bit");
    #(CPB*5);
  endtask
  task check_reply(input integer p);
    reg [7:0] value;
    for(integer i=0;i<REPLY_BYTES;i=i+1) begin
      receive_byte(value);
      if(i==0 && value!==8'h5a) $fatal(1,"header0");
      if(i==1 && value!==8'ha5) $fatal(1,"header1");
      if(i==2 && value!=={5'b0,cs[p]}) $fatal(1,"class");
      if(i>=3 && value!=={4'b0,ss[p][(i-3)*4+:4]}) $fatal(1,"score");
    end
    reply_end=$time;
  endtask
  initial begin
    $readmemh("x.hex",xs); $readmemh("exp_scores.hex",ss);
    $readmemh("exp_class.hex",cs);
    repeat(5) @(negedge clk); rst=0;
    for(packet=0;packet<N;packet=packet+1) begin
      wait(dut.state==0);
      @(negedge clk); req_start=$time;
      fork
        begin
          send_byte(8'ha5); send_byte(8'h5a);
          send_byte(xs[packet][7:0]); send_byte({3'b0,xs[packet][12:8]});
        end
        check_reply(packet);
      join
      if(reply_end-req_start >= (REQUEST_BYTES+REPLY_BYTES)*10*CPB*10)
        $fatal(1,"Expected overlapping request tail/reply: wire sum is not a bound");
      if(packet==0) first_wall=(reply_end-req_start)/10.0;
      else if((reply_end-req_start)/10.0 != first_wall)
        $fatal(1,"Unexpected packet latency variation");
    end
    $display("PASS independent UART boundaries: 3 exact replies, overlapping stop tail");
    $finish;
  end
  initial begin #1000000; $fatal(1,"timeout"); end
endmodule
"""
    (tmp_path / "tb_uart_boundary.sv").write_text(tb)
    build = subprocess.run(["iverilog", "-g2012", "-s", "tb_uart_boundary", "-o", "uart_sim",
                            "tb_uart_boundary.sv", "dlgn_top.sv", "uart.sv", "dlgn_uart.sv"],
                           cwd=tmp_path, capture_output=True, text=True, timeout=60)
    assert build.returncode == 0, build.stdout + build.stderr
    sim = subprocess.run(["vvp", "uart_sim"], cwd=tmp_path,
                         capture_output=True, text=True, timeout=60)
    assert sim.returncode == 0, sim.stdout + sim.stderr
    assert "PASS independent UART boundaries: 3 exact replies" in sim.stdout


@pytest.mark.parametrize("pipeline", [False, True])
def test_production_performance_bench_finishes_full_reply_stop_bit(tmp_path, pipeline):
    """Exercise the shipped bench, including the DRAIN/ready NBA transition."""
    if not shutil.which("iverilog") or not shutil.which("vvp"):
        pytest.skip("Icarus required for production performance-bench check")
    rng = np.random.default_rng(2102028)
    net = dict(in_dim=13, width=40, depth=1, n_classes=5, tau=1,
               layers=[dict(ia=rng.integers(13, size=40).tolist(),
                            ib=rng.integers(13, size=40).tolist(),
                            gates=(np.arange(40) % 16).tolist())])
    params = export_uart(net, rng.integers(2, size=(8, 13)).astype(bool), tmp_path,
                         pipeline=pipeline, head_pipeline=True)
    shutil.copyfile(ROOT / "rtl/tb_performance.sv", tmp_path / "tb_dlgn.sv")
    definitions = {k: params[k] for k in ("IN", "K", "SW", "CW", "LAT")}
    definitions.update(NCORE=8, NUART=2, NV=8, CPB=104, INPUT_BYTES=2)
    (tmp_path / "performance_params.svh").write_text(
        "\n".join(f"parameter {k}={v};" for k, v in definitions.items())+"\n")
    build = subprocess.run(["iverilog", "-g2012", "-s", "tb_dlgn", "-o", "production_sim",
                            "tb_dlgn.sv", "dlgn_top.sv"], cwd=tmp_path,
                           capture_output=True, text=True, timeout=60)
    assert build.returncode == 0, build.stdout + build.stderr
    sim = subprocess.run(["vvp", "production_sim"], cwd=tmp_path,
                         capture_output=True, text=True, timeout=60)
    assert sim.returncode == 0, sim.stdout + sim.stderr
    assert "PASS: core and UART performance boundaries checked" in sim.stdout
    assert f"stages={params['LAT']} port_cycles={params['LAT']-1} capture_cycles={params['LAT']} ii_cycles=1" in sim.stdout
    records = re.findall(r"UART index=(\d+) start_half_cycles=(\d+) complete_half_cycles=(\d+) bytes=(\d+)", sim.stdout)
    assert len(records) == 2
    decoded = [tuple(map(int, record)) for record in records]
    nominal_wire_sum_cycles = (4+8)*10*104
    for i, (index, start, stop, nbytes) in enumerate(decoded):
        assert index == i and nbytes == 8
        # The full reply stops before the sum of directional serial work,
        # because RX recognizes the final request stop bit at its midpoint.
        assert nominal_wire_sum_cycles*2-104 < stop-start < nominal_wire_sum_cycles*2
    assert decoded[1][1] > decoded[0][2]
