// Cycle measurements only. The arbitrary 10 ns simulation clock is not Fmax.
`timescale 1ns/1ps
`include "performance_params.svh"
`include "uart.sv"
`include "dlgn_uart.sv"
`include "board_top.sv"
module tb_dlgn;
  reg clk=0, rst=1, in_valid=0, rx_pin=1;
  reg [IN-1:0] x=0;
  wire out_valid, tx_pin, monitor_valid, monitor_error;
  wire [7:0] monitor_data;
  wire [CW-1:0] class_out;
  wire [K*SW-1:0] scores;
  reg [IN-1:0] xmem[0:NV-1];
  reg [K*SW-1:0] smem[0:NV-1];
  reg [CW-1:0] cmem[0:NV-1];
  integer accepted[0:NCORE-1];
  integer cycle=0, nin=0, nout=0, consumed=0, last_output=-1;
  integer port_cycles=-1, capture_cycles=-1, uart_index=0, reply_count=0;
  time request_started;
  dlgn_top core(.clk(clk),.rst(rst),.in_valid(in_valid),.x(x),
                .out_valid(out_valid),.class_out(class_out),.scores(scores));
  board_top serial_board(.clk(clk),.button_n(!rst),.uart_rx_pin(rx_pin),.uart_tx_pin(tx_pin));
  uart_rx #(.CLKS_PER_BIT(CPB)) reply_monitor(
    .clk(clk),.rst(rst),.rx(tx_pin),.data(monitor_data),
    .valid(monitor_valid),.error(monitor_error));
  always #5 clk=~clk;
  always @(posedge clk) begin
    cycle=cycle+1;
    if (!rst && in_valid) begin accepted[nin]=cycle; nin=nin+1; end
    // A downstream register sees the output from before this edge's NBA.
    if (!rst && out_valid) begin
      if(consumed>=NCORE) $fatal(1,"Extra downstream result");
      capture_cycles=cycle-accepted[consumed];
      if(capture_cycles!=LAT || scores!==smem[consumed] || class_out!==cmem[consumed])
        $fatal(1,"Downstream latency/payload mismatch");
      consumed=consumed+1;
    end
    #1;
    if(!rst && out_valid) begin
      if(nout>=nin) $fatal(1,"Output without input");
      port_cycles=cycle-accepted[nout];
      if(port_cycles!=LAT-1 || scores!==smem[nout] || class_out!==cmem[nout])
        $fatal(1,"Port latency/payload mismatch");
      if(last_output>=0 && cycle-last_output!=1) $fatal(1,"Core II is not one");
      last_output=cycle; nout=nout+1;
    end
    if(!rst && monitor_error) $fatal(1,"Reply framing error");
    if(!rst && monitor_valid) begin
      if(reply_count>=K+3) $fatal(1,"Extra reply byte");
      case(reply_count)
        0: if(monitor_data!==8'h5a) $fatal(1,"Reply header0");
        1: if(monitor_data!==8'ha5) $fatal(1,"Reply header1");
        2: if(monitor_data!==8'(cmem[uart_index])) $fatal(1,"Reply class");
        default: if(monitor_data!==8'(smem[uart_index][(reply_count-3)*SW +: SW]))
                   $fatal(1,"Reply score");
      endcase
      reply_count=reply_count+1;
    end
    if(cycle>NCORE+NUART*(INPUT_BYTES+K+5)*CPB*12+1000) $fatal(1,"Timeout");
  end
  task send_byte(input reg [7:0] b);
    rx_pin=0; repeat(CPB) @(negedge clk);
    for(integer bit_index=0;bit_index<8;bit_index=bit_index+1) begin
      rx_pin=b[bit_index]; repeat(CPB) @(negedge clk);
    end
    rx_pin=1; repeat(CPB) @(negedge clk);
  endtask
  initial begin
    $readmemh("x.hex",xmem); $readmemh("exp_scores.hex",smem);
    $readmemh("exp_class.hex",cmem);
    repeat(5) @(negedge clk); rst=0;
    for(integer i=0;i<NCORE;i=i+1) begin
      @(negedge clk); in_valid=1; x=xmem[i];
    end
    @(negedge clk); in_valid=0;
    wait(nout==NCORE && consumed==NCORE);
    $display("CORE vectors=%0d stages=%0d port_cycles=%0d capture_cycles=%0d ii_cycles=1",
             nout,LAT,port_cycles,capture_cycles);
    for(uart_index=0;uart_index<NUART;uart_index=uart_index+1) begin
      @(negedge clk); reply_count=0; request_started=$time;
      send_byte(8'ha5); send_byte(8'h5a);
      for(integer b=0;b<INPUT_BYTES;b=b+1) send_byte(8'(xmem[uart_index] >> (8*b)));
      // DRAIN with transmitter ready is the end of the final full stop bit.
      // A UART decoder's valid pulse happens earlier, around stop-bit midpoint.
      wait(serial_board.board.adapter.state==5);
      // State and transmitter counters update in separate NBA assignments.
      // Observe the last byte busy before its ready transition; otherwise a
      // delta-cycle transient can look like the end of that byte.
      wait(!serial_board.board.adapter.transmitter.ready);
      wait(serial_board.board.adapter.transmitter.ready);
      if(reply_count!=K+3) $fatal(1,"Missing reply bytes");
      $display("UART index=%0d start_half_cycles=%0d complete_half_cycles=%0d bytes=%0d",
               uart_index,request_started/5,$time/5,reply_count);
    end
    $display("PASS: core and UART performance boundaries checked");
    $finish;
  end
endmodule
