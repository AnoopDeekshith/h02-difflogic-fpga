"""Bit-exact hard-gate reference model (pure NumPy, no PyTorch).

This is the golden model the RTL must match bit for bit: same gate
truth tables, same popcount per class, same argmax tie-break
(lowest class index wins, exactly like the RTL's strict '>' scan).
"""
import json
import numpy as np


def load(path):
    with open(path) as f:
        return json.load(f)


def forward_bits(net, x_bits):
    """x_bits: (N, in_dim) bool. Returns list of per-layer outputs (bool)."""
    h = np.asarray(x_bits, dtype=bool)
    outs = []
    for L in net["layers"]:
        a = h[:, L["ia"]].astype(np.uint8)
        b = h[:, L["ib"]].astype(np.uint8)
        ids = np.asarray(L["gates"], dtype=np.uint8)[None, :]
        h = ((ids >> (3 - (2 * a + b))) & 1).astype(bool)
        outs.append(h)
    return outs


def scores(net, x_bits):
    """Integer class scores (popcount per group), shape (N, k)."""
    last = forward_bits(net, x_bits)[-1]
    k = net["n_classes"]
    return last.reshape(last.shape[0], k, -1).sum(-1).astype(np.int64)


def predict(net, x_bits):
    return scores(net, x_bits).argmax(1)   # np.argmax returns first max


def toggle_rate(net, x_bits):
    """Measured average toggles per gate per new input, for consecutive
    samples in the given order. Useful as a software cross-check of the
    zero-delay activity in your SAIF (glitches will add on top in RTL)."""
    outs = forward_bits(net, x_bits)
    h = np.concatenate(outs, axis=1)
    return (h[1:] != h[:-1]).mean()
