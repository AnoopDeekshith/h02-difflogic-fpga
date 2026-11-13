// UART 8N1, least-significant bit first. CLKS_PER_BIT must be >= 8.
module uart_rx #(
    parameter integer CLKS_PER_BIT = 104
) (
    input wire clk, rst, rx,
    output reg [7:0] data,
    output reg valid, error
);
    localparam integer TW = $clog2(CLKS_PER_BIT);
    localparam IDLE=0, START=1, DATA=2, STOP=3, RECOVER=4;
    (* async_reg = "true" *) reg rx_meta, rx_sync;
    reg [2:0] state;
    reg [TW-1:0] timer;
    reg [2:0] bit_index;
    reg [7:0] shift;
    always @(posedge clk) begin
        if (rst) begin
            rx_meta <= 1; rx_sync <= 1;
        end else begin
            rx_meta <= rx; rx_sync <= rx_meta;
        end
        valid <= 0;
        error <= 0;
        if (rst) begin
            state <= IDLE; timer <= 0; bit_index <= 0;
            shift <= 0; data <= 0;
        end else case (state)
            IDLE: if (!rx_sync) begin
                timer <= CLKS_PER_BIT/2 - 1; state <= START;
            end
            START: if (timer != 0) timer <= timer - 1'b1;
                else if (rx_sync) begin state <= IDLE; error <= 1; end
                else begin
                    timer <= CLKS_PER_BIT - 1; bit_index <= 0; state <= DATA;
                end
            DATA: if (timer != 0) timer <= timer - 1'b1;
                else begin
                    shift[bit_index] <= rx_sync;
                    timer <= CLKS_PER_BIT - 1;
                    if (bit_index == 7) state <= STOP;
                    else bit_index <= bit_index + 1'b1;
                end
            STOP: if (timer != 0) timer <= timer - 1'b1;
                else if (rx_sync) begin
                    data <= shift; valid <= 1; state <= IDLE;
                end else begin error <= 1; state <= RECOVER; end
            RECOVER: if (rx_sync) state <= IDLE;
            default: state <= IDLE;
        endcase
    end
endmodule

module uart_tx #(
    parameter integer CLKS_PER_BIT = 104
) (
    input wire clk, rst,
    input wire [7:0] data,
    input wire valid,
    output wire ready,
    output wire tx
);
    localparam integer TW = $clog2(CLKS_PER_BIT);
    reg [TW-1:0] timer;
    reg [3:0] bits_left;
    reg [9:0] shift;
    assign ready = (bits_left == 0);
    assign tx = ready ? 1'b1 : shift[0];
    always @(posedge clk) begin
        if (rst) begin timer <= 0; bits_left <= 0; shift <= 10'h3ff; end
        else if (ready) begin
            if (valid) begin
                shift <= {1'b1, data, 1'b0};
                bits_left <= 10; timer <= CLKS_PER_BIT - 1;
            end
        end else if (timer != 0) timer <= timer - 1'b1;
        else begin
            timer <= CLKS_PER_BIT - 1;
            shift <= {1'b1, shift[9:1]};
            bits_left <= bits_left - 1'b1;
        end
    end
endmodule
