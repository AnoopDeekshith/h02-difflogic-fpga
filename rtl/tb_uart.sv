// Byte-level end-to-end test: UART pins -> adapter -> real DLGN -> UART pins.
`timescale 1ns/1ps
`include "uart.sv"
`include "dlgn_uart.sv"
module tb_dlgn;
    `include "uart_params.svh"
    localparam INPUT_BYTES=(IN+7)/8, REPLY_BYTES=K+3;
    localparam TIMEOUT_CYCLES=CPB*40;
    reg clk=0, rst=1, rx=1;
    wire tx;
    reg [IN-1:0] xmem [N];
    reg [K*SW-1:0] smem [N];
    reg [CW-1:0] cmem [N];
    integer nout=0, response_index=0, cycles=0;
    reg [7:0] response_byte, expected_byte;
    icebreaker_top #(.IN(IN), .K(K), .SW(SW), .CW(CW),
        .CLKS_PER_BIT(CPB), .RX_TIMEOUT_CYCLES(TIMEOUT_CYCLES)) dut (
        .clk(clk), .button_n(~rst), .uart_rx_pin(rx), .uart_tx_pin(tx));
    always #5 clk=~clk;
    always @(posedge clk) begin
        cycles <= cycles+1;
        if (cycles > (N+10)*(INPUT_BYTES+REPLY_BYTES+10)*12*(CPB+1))
            $fatal(1, "UART test timeout: %0d/%0d replies", nout, N);
    end

    // Drive off the sampling edge. DELTA tests baud mismatch at realistic CPB.
    task automatic send_byte(input reg [7:0] value, input integer delta=0,
                             input reg good_stop=1);
        @(negedge clk); rx=0;
        repeat(CPB+delta) @(negedge clk);
        for (integer b=0; b<8; b=b+1) begin
            rx=value[b]; repeat(CPB+delta) @(negedge clk);
        end
        rx=good_stop;
        repeat(CPB+delta) @(negedge clk);
        rx=1;
    endtask
    task automatic reset_adapter;
        @(negedge clk); rst=1; rx=1;
        repeat(8) @(negedge clk);
        rst=0;
        repeat(CPB*2) @(negedge clk);
    endtask

    // Independent UART decoder checks every byte, including all class scores.
    initial begin
        forever begin
            @(negedge tx);
            if (!rst) begin
                repeat(CPB + CPB/2) @(negedge clk);
                for (integer b=0; b<8; b=b+1) begin
                    response_byte[b]=tx;
                    repeat(CPB) @(negedge clk);
                end
                if (tx !== 1'b1) $fatal(1, "TX stop bit is invalid");
                if (nout >= N) $fatal(1, "Unexpected extra response");
                if (response_index == 0) expected_byte=8'h5a;
                else if (response_index == 1) expected_byte=8'ha5;
                else if (response_index == 2) expected_byte=8'(cmem[nout]);
                else expected_byte=8'(smem[nout] >> ((response_index-3)*SW));
                // Only SW bits of each packed reference score belong to this class.
                if (response_index >= 3) expected_byte=expected_byte & ((1<<SW)-1);
                if (response_byte !== expected_byte)
                    $fatal(1, "Reply %0d byte %0d: got %h expected %h",
                        nout, response_index, response_byte, expected_byte);
                if (response_index == REPLY_BYTES-1) begin
                    response_index=0; nout=nout+1;
                end else response_index=response_index+1;
            end
        end
    end

    initial begin
        $readmemh("x.hex", xmem);
        $readmemh("exp_scores.hex", smem);
        $readmemh("exp_class.hex", cmem);
        reset_adapter();
        // Noise and overlapping header prefixes must not launch inference.
        send_byte(8'h33); send_byte(8'h5a);
        // Truncated header times out.
        send_byte(8'ha5);
        repeat(TIMEOUT_CYCLES+CPB*2) @(negedge clk);
        // Truncated image times out.
        send_byte(8'ha5); send_byte(8'h5a);
        if (INPUT_BYTES>1) send_byte(8'hff);
        repeat(TIMEOUT_CYCLES+CPB*2) @(negedge clk);
        // Framing error discards a partially collected image.
        send_byte(8'ha5); send_byte(8'h5a); send_byte(8'hff, 0, 0);
        repeat(CPB*3) @(negedge clk);
        // Reset during a partial request discards it as well.
        send_byte(8'ha5); send_byte(8'h5a);
        reset_adapter();
        if (nout != 0 || tx !== 1'b1) $fatal(1, "Aborted requests produced a reply");

        for (integer n=0; n<N; n=n+1) begin
            // Alternate small baud errors when testing the real 104-cycle divider.
            send_byte(8'ha5);
            send_byte(8'ha5); // overlapping sync prefix
            send_byte(8'h5a);
            for (integer j=0; j<INPUT_BYTES; j=j+1) begin
                send_byte(8'(xmem[n] >> (8*j)), (CPB>=100) ? (n%3)-1 : 0);
                if (j==0) repeat(CPB*2) @(negedge clk); // legal inter-byte gap
            end
            wait(nout==n+1);
            repeat(CPB*2) @(negedge clk); // allow last stop bit to finish
        end
        repeat(CPB*20) @(negedge clk);
        if (nout != N) $fatal(1, "Wrong response count");
        $display("PASS: %0d/%0d UART images bit-exact (scores + class); recovery checks passed", nout, N);
        $finish;
    end
endmodule
