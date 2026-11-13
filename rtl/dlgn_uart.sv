// Request: A5 5A, then ceil(IN/8) image bytes (lowest bits first).
// Reply:   5A A5, class byte, then K score bytes (class 0 first).
// One outstanding request: host must wait for the whole reply before sending.
module dlgn_uart #(
    parameter integer IN = 192, K = 10, SW = 7, CW = 4,
    parameter integer CLKS_PER_BIT = 104,
    parameter integer RX_TIMEOUT_CYCLES = 3000000
) (
    input wire clk, rst, uart_rx_pin,
    output wire uart_tx_pin
);
    localparam integer INPUT_BYTES = (IN + 7)/8;
    localparam integer REPLY_BYTES = K + 3;
    localparam integer IW = (INPUT_BYTES > 1) ? $clog2(INPUT_BYTES) : 1;
    localparam integer RW = $clog2(REPLY_BYTES);
    localparam integer TW = $clog2(RX_TIMEOUT_CYCLES);
    localparam HEAD0=0, HEAD1=1, PAYLOAD=2, RESULT=3, SEND=4, DRAIN=5;
    reg [2:0] state;
    reg [IW-1:0] input_index;
    reg [RW-1:0] reply_index;
    reg [TW-1:0] idle_count;
    reg [INPUT_BYTES*8-1:0] image;
    reg [REPLY_BYTES*8-1:0] reply;
    reg core_valid;
    wire [7:0] rx_data;
    wire rx_valid, rx_error, tx_ready, result_valid;
    wire [CW-1:0] result_class;
    wire [K*SW-1:0] result_scores;

    uart_rx #(.CLKS_PER_BIT(CLKS_PER_BIT)) receiver (
        .clk(clk), .rst(rst), .rx(uart_rx_pin),
        .data(rx_data), .valid(rx_valid), .error(rx_error));
    uart_tx #(.CLKS_PER_BIT(CLKS_PER_BIT)) transmitter (
        .clk(clk), .rst(rst), .data(reply[7:0]),
        .valid(state == SEND), .ready(tx_ready), .tx(uart_tx_pin));
    dlgn_top core (
        .clk(clk), .rst(rst), .in_valid(core_valid), .x(image[IN-1:0]),
        .out_valid(result_valid), .class_out(result_class), .scores(result_scores));

    always @(posedge clk) begin
        core_valid <= 0;
        if (rst) begin
            state <= HEAD0; input_index <= 0; reply_index <= 0;
            idle_count <= 0; image <= 0; reply <= 0;
        end else if ((state == HEAD1 || state == PAYLOAD) &&
                     (rx_error || idle_count == RX_TIMEOUT_CYCLES-1)) begin
            // Discard an incomplete frame on UART errors or a long byte gap.
            state <= HEAD0; input_index <= 0; idle_count <= 0;
        end else begin
            if (rx_valid || (state != HEAD1 && state != PAYLOAD)) idle_count <= 0;
            else idle_count <= idle_count + 1'b1;
            case (state)
                HEAD0: if (rx_valid && rx_data == 8'ha5) state <= HEAD1;
                HEAD1: if (rx_valid) begin
                    if (rx_data == 8'h5a) begin state <= PAYLOAD; input_index <= 0; end
                    else if (rx_data != 8'ha5) state <= HEAD0;
                end
                PAYLOAD: if (rx_valid) begin
                    image[input_index*8 +: 8] <= rx_data;
                    if (input_index == INPUT_BYTES-1) begin
                        core_valid <= 1; state <= RESULT;
                    end else input_index <= input_index + 1'b1;
                end
                RESULT: if (result_valid) begin
                    reply[7:0] <= 8'h5a;
                    reply[15:8] <= 8'ha5;
                    reply[23:16] <= 8'(result_class);
                    for (integer k=0; k<K; k=k+1)
                        reply[(k+3)*8 +: 8] <= 8'(result_scores[k*SW +: SW]);
                    reply_index <= 0; state <= SEND;
                end
                SEND: if (tx_ready) begin
                    reply <= reply >> 8;
                    if (reply_index == REPLY_BYTES-1) state <= DRAIN;
                    else reply_index <= reply_index + 1'b1;
                end
                DRAIN: if (tx_ready) state <= HEAD0;
                default: state <= HEAD0;
            endcase
        end
    end
endmodule

// Physical pins: clock, active-low button reset, serial RX, serial TX.
module icebreaker_top #(
    parameter integer IN = 192, K = 10, SW = 7, CW = 4,
    parameter integer CLKS_PER_BIT = 104,
    parameter integer RX_TIMEOUT_CYCLES = 3000000
) (
    input wire clk, button_n, uart_rx_pin,
    output wire uart_tx_pin
);
    // Power-on reset plus asynchronous assertion / synchronous release.
    (* async_reg = "true" *) reg [1:0] reset_pipe = 2'b11;
    always @(posedge clk or negedge button_n) begin
        if (!button_n) reset_pipe <= 2'b11;
        else reset_pipe <= {reset_pipe[0], 1'b0};
    end
    dlgn_uart #(.IN(IN), .K(K), .SW(SW), .CW(CW),
                .CLKS_PER_BIT(CLKS_PER_BIT),
                .RX_TIMEOUT_CYCLES(RX_TIMEOUT_CYCLES)) adapter (
        .clk(clk), .rst(reset_pipe[1]),
        .uart_rx_pin(uart_rx_pin), .uart_tx_pin(uart_tx_pin));
endmodule
