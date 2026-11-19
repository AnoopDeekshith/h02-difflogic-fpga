"""A small, dependency-free differentiable logic gate network (DLGN).

Mirrors the difflogic library's semantics (LogicLayer + GroupSum, same
gate order, same random-connection scheme) in plain PyTorch, so it runs
on CPU, on Colab, or anywhere difflogic's CUDA extension won't build.
If you train with difflogic instead, dlgn/difflogic_import.py converts
that model into the same JSON the exporter reads.
"""
import json
import math
import torch
import torch.nn as nn
import torch.nn.functional as F

from .gates import soft_gates


class LogicLayer(nn.Module):
    def __init__(self, in_dim: int, out_dim: int, generator: torch.Generator):
        super().__init__()
        self.in_dim, self.out_dim = in_dim, out_dim
        # difflogic's "random" connections: every input gets used at least
        # once when 2*out_dim >= in_dim.
        c = torch.randperm(2 * out_dim, generator=generator) % in_dim
        c = c[torch.randperm(2 * out_dim, generator=generator)]
        self.register_buffer("ia", c[:out_dim].clone())
        self.register_buffer("ib", c[out_dim:].clone())
        self.weights = nn.Parameter(torch.randn(out_dim, 16, generator=generator))
        self.hard = False          # True -> use argmax gate (discretized model)
        self.last_out = None       # kept for the activity penalty

    def forward(self, x):
        g = soft_gates(x[:, self.ia], x[:, self.ib])          # (N, out, 16)
        if self.hard:
            w = F.one_hot(self.weights.argmax(-1), 16).to(g.dtype)
        else:
            w = F.softmax(self.weights, dim=-1)
        y = (g * w).sum(-1)
        self.last_out = y
        return y

    def gate_ids(self):
        return self.weights.argmax(-1)


class GroupSum(nn.Module):
    """Class score = (number of 1s in that class's output group) / tau."""

    def __init__(self, k: int, tau: float):
        super().__init__()
        self.k, self.tau = k, tau

    def forward(self, x):
        return x.reshape(x.shape[0], self.k, -1).sum(-1) / self.tau


class DLGN(nn.Module):
    def __init__(self, in_dim, width, depth, n_classes, tau, seed=0):
        super().__init__()
        assert width % n_classes == 0, "width must be divisible by n_classes"
        gen = torch.Generator().manual_seed(seed)
        dims = [in_dim] + [width] * depth
        self.layers = nn.ModuleList(
            LogicLayer(dims[i], dims[i + 1], gen) for i in range(depth))
        self.head = GroupSum(n_classes, tau)
        self.cfg = dict(in_dim=in_dim, width=width, depth=depth,
                        n_classes=n_classes, tau=tau, seed=seed)

    def set_hard(self, hard: bool):
        for l in self.layers:
            l.hard = hard

    def forward(self, x):
        for l in self.layers:
            x = l(x)
        return self.head(x)

    # ---------------------------------------------------------------
    # Power-aware term (your stretch idea)
    # ---------------------------------------------------------------
    def activity_penalty(self, mode: str = "batch", layer_weights=None):
        """Differentiable estimate of switching activity, averaged over gates.

        mode="batch"  (recommended): p_g = mean over the batch of gate g's
            soft output, i.e. the probability g outputs 1 across the input
            distribution. If consecutive inputs are independent, the
            expected zero-delay toggle probability is alpha_g = 2 p_g (1-p_g).
            This is a training surrogate, not measured SAIF activity or power.
            Actual transitions depend on input order; mapped nets, glitches,
            clocking and capacitances need separate hardware evaluation.
        mode="sample": mean of 2 a (1 - a) per sample. This is NOT activity;
            it penalizes undecided soft outputs and mostly pushes the
            network toward discreteness. Keep it only as an ablation.

        layer_weights=None keeps the original mean over all gates. A list of
        nonnegative per-layer weights (one per logic layer, positive sum)
        returns sum_l w_l * mean_l(alpha) / sum_l w_l, e.g. [0, 0, 0, 1]
        penalizes only the last layer (step 4.15 targeting experiment).
        """
        if layer_weights is not None:
            w = [float(v) for v in layer_weights]
            if (len(w) != len(self.layers) or not all(math.isfinite(v) for v in w)
                    or min(w) < 0 or sum(w) <= 0):
                raise ValueError("layer_weights needs one nonnegative weight per layer, positive sum")
        terms = []
        for l in self.layers:
            a = l.last_out
            if mode == "batch":
                p = a.mean(0)
                terms.append(2 * p * (1 - p))
            else:
                terms.append((2 * a * (1 - a)).mean(0))
        if layer_weights is None:
            return torch.cat(terms).mean()
        return sum(wl * t.mean() for wl, t in zip(w, terms)) / sum(w)

    # ---------------------------------------------------------------
    def to_json(self, path):
        """The hand-off format read by dlgn/hard.py and dlgn/export_verilog.py."""
        d = dict(self.cfg)
        d["layers"] = [dict(ia=l.ia.tolist(), ib=l.ib.tolist(),
                            gates=l.gate_ids().tolist()) for l in self.layers]
        with open(path, "w") as f:
            json.dump(d, f)
        return d
