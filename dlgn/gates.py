"""The 16 two-input logic gates, in the exact order of Table 1 in
Petersen et al., NeurIPS 2022 (and of the difflogic library).

Handy property of this ordering: writing the truth table as the 4-bit
string  f(0,0) f(0,1) f(1,0) f(1,1)  (MSB first) gives the gate ID.
  AND = 0001 = 1, XOR = 0110 = 6, OR = 0111 = 7, NAND = 1110 = 14.
So  f_id(a, b) = (id >> (3 - (2a + b))) & 1.
That single rule is what the hard evaluator uses, and the Verilog
expressions below are checked against it in tests/test_gates.py.
"""
GATE_NAMES = [
    "FALSE", "A_AND_B", "A_AND_NOT_B", "A", "NOT_A_AND_B", "B", "XOR", "OR",
    "NOR", "XNOR", "NOT_B", "A_OR_NOT_B", "NOT_A", "NOT_A_OR_B", "NAND", "TRUE",
]

# Verilog expression for each gate; {a} and {b} are substituted with nets.
VERILOG_EXPR = [
    "1'b0",
    "{a} & {b}",
    "{a} & ~{b}",
    "{a}",
    "~{a} & {b}",
    "{b}",
    "{a} ^ {b}",
    "{a} | {b}",
    "~({a} | {b})",
    "~({a} ^ {b})",
    "~{b}",
    "{a} | ~{b}",
    "~{a}",
    "~{a} | {b}",
    "~({a} & {b})",
    "1'b1",
]


def truth(gate_id: int, a: int, b: int) -> int:
    """Hard output of gate `gate_id` for Boolean inputs a, b."""
    return (gate_id >> (3 - (2 * a + b))) & 1


def soft_gates(a, b):
    """All 16 probabilistic relaxations (Table 1). Returns shape (..., 16).

    Each entry is the probability the gate outputs 1 when its inputs are
    independent Bernoulli(a) and Bernoulli(b). At a, b in {0, 1} these are
    exactly the truth tables.
    """
    import torch   # imported here so the RTL tools don't need PyTorch
    ab = a * b
    return torch.stack([
        torch.zeros_like(a),      # 0  FALSE
        ab,                       # 1  A AND B
        a - ab,                   # 2  A AND NOT B
        a,                        # 3  A
        b - ab,                   # 4  NOT A AND B
        b,                        # 5  B
        a + b - 2 * ab,           # 6  XOR
        a + b - ab,               # 7  OR
        1 - (a + b - ab),         # 8  NOR
        1 - (a + b - 2 * ab),     # 9  XNOR
        1 - b,                    # 10 NOT B
        1 - b + ab,               # 11 A OR NOT B   (B implies A)
        1 - a,                    # 12 NOT A
        1 - a + ab,               # 13 NOT A OR B   (A implies B)
        1 - ab,                   # 14 NAND
        torch.ones_like(a),       # 15 TRUE
    ], dim=-1)
