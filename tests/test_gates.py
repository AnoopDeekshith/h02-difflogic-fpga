"""Gate table consistency: truth() rule == Verilog expressions == soft
relaxation at Boolean corners. Run: python -m pytest tests -q"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dlgn.gates import VERILOG_EXPR, truth   # noqa: E402

# reference truth tables from Table 1 of the paper, columns 00 01 10 11
PAPER = ["0000", "0001", "0010", "0011", "0100", "0101", "0110", "0111",
         "1000", "1001", "1010", "1011", "1100", "1101", "1110", "1111"]


def _eval_verilog(expr, a, b):
    e = expr.format(a="A", b="B").replace("1'b0", "0").replace("1'b1", "1")
    return eval(e, {}, {"A": a, "B": b}) & 1  # python ~x & 1 == 1-bit NOT


def test_truth_matches_paper_and_verilog():
    for g in range(16):
        for col, (a, b) in enumerate([(0, 0), (0, 1), (1, 0), (1, 1)]):
            exp = int(PAPER[g][col])
            assert truth(g, a, b) == exp, (g, a, b)
            assert _eval_verilog(VERILOG_EXPR[g], a, b) == exp, (g, a, b)


def test_soft_corners():
    try:
        import torch
    except ImportError:
        return
    from dlgn.gates import soft_gates
    for a in (0.0, 1.0):
        for b in (0.0, 1.0):
            s = soft_gates(torch.tensor([a]), torch.tensor([b]))[0]
            for g in range(16):
                assert float(s[g]) == truth(g, int(a), int(b))
