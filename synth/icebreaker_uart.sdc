# iCEBreaker oscillator: 12 MHz, period = 1000 / 12 ns.
create_clock -name clk12 -period 83.333333333333 [get_ports clk]
# RX and button are asynchronous inputs, not clocks.
# Do not add blanket false paths: nextpnr's generic SDC false-path command is
# currently a no-op. See docs/steps/2.7-clock-and-pin-constraints.md.
