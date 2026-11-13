// Small toolchain check, independent of the trained neural network.
// A registered counter provides real register-to-register timing paths.
module timing_smoke (
    input wire clk,
    output wire led_n
);
    reg [23:0] count = 24'b0;
    always @(posedge clk) count <= count + 1'b1;
    assign led_n = ~count[23];
endmodule
