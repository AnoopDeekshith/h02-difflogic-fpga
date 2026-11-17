// Full ordered core workload for step 3.3. Zero-delay RTL, not physical power.
`timescale 1ps/1ps
`include "capture_params.svh"
module tb_capture;
  logic clk = 0, rst = 1, in_valid = 0;
  logic [IN-1:0] x = '0;
  wire out_valid;
  wire [CW-1:0] class_out;
  wire [K*SW-1:0] scores;
  logic [IN-1:0] xmem [N];
  logic [K*SW-1:0] smem [N];
  logic [CW-1:0] cmem [N];
  integer input_index = -1, output_index = -1;
  integer input_count = 0, output_count = 0, cycle_index = 0;
  integer events;
  logic capture_done = 0;

  dlgn_top dut (.clk, .rst, .in_valid, .x, .out_valid, .class_out, .scores);
  // 41,667 ps half-period: nominal 12 MHz rounded to a 1 ps time grid.
  always #(HALF_PERIOD_PS) clk = ~clk;

  initial begin
    $readmemh("x.hex", xmem);
    $readmemh("exp_scores.hex", smem);
    $readmemh("exp_class.hex", cmem);
    events = $fopen("events.csv", "w");
    if (!events) $fatal(1, "Cannot open events.csv");
    $fdisplay(events, "kind,index,time_ps,cycle");
    $dumpfile("dlgn.vcd");
    $dumpvars(0, dut);
    $dumpvars(0, input_index, output_index, input_count, output_count,
                 cycle_index, capture_done);
    // Drive at falling edges; sample settled outputs 1 ps after rising edges.
    repeat (3) @(negedge clk);
    rst = 0;
    for (int i=0; i<N; i++) begin
      x = xmem[i];
      input_index = i;
      in_valid = 1;
      @(negedge clk);
    end
    in_valid = 0;
    input_index = -1;
    // Hold the last image throughout drain. No extra invalid input toggles.
    wait (output_count == N);
    repeat (3) @(negedge clk);
    if (input_count != N || output_count != N || out_valid !== 1'b0)
      $fatal(1, "Incorrect final counts or valid drain");
    capture_done = 1;
    $fdisplay(events, "done,-1,%0t,%0d", $time, cycle_index);
    $fclose(events);
    $display("PASS: %0d/%0d baseline vectors bit-exact (scores + class)", output_count, N);
    #1;
    $finish;
  end

  always @(posedge clk) begin
    cycle_index = cycle_index + 1;
    if (cycle_index > N + LAT + 20) $fatal(1, "Capture timeout");
    if (!rst && in_valid) begin
      if (input_index != input_count || input_count >= N)
        $fatal(1, "Input index/count mismatch");
      $fdisplay(events, "input,%0d,%0t,%0d", input_index, $time, cycle_index);
      input_count = input_count + 1;
    end
    #1;
    if (!rst && out_valid) begin
      if (output_count >= N) $fatal(1, "Unexpected extra output");
      if (scores !== smem[output_count] || class_out !== cmem[output_count])
        $fatal(1, "MISMATCH index=%0d class=%0d expected=%0d scores=%h expected=%h",
               output_count, class_out, cmem[output_count], scores, smem[output_count]);
      output_index = output_count;
      $fdisplay(events, "output,%0d,%0t,%0d", output_index, $time, cycle_index);
      output_count = output_count + 1;
    end
  end
endmodule
