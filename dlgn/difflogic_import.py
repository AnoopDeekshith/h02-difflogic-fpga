"""Convert a model trained with the official difflogic library
(github.com/Felix-Petersen/difflogic) into this repo's JSON format,
so the same hard evaluator, Verilog exporter and testbench apply.

Untested here (difflogic needs its CUDA extension built); written against
difflogic's public attributes: LogicLayer.indices = (a, b) and
LogicLayer.weights of shape (out_dim, 16), GroupSum.k and .tau. Its gate
order is the paper's Table 1, same as dlgn/gates.py. After converting,
check that the hard accuracy from difflogic's own eval mode equals
dlgn.hard.predict on the same input bits.
"""
import json


def to_json(model, in_dim, path, seed=None):
    from difflogic import LogicLayer, GroupSum
    layers, head = [], None
    for m in model.modules():
        if isinstance(m, LogicLayer):
            a, b = m.indices
            layers.append(dict(ia=a.tolist(), ib=b.tolist(),
                               gates=m.weights.argmax(-1).tolist()))
        elif isinstance(m, GroupSum):
            head = m
    d = dict(in_dim=in_dim, width=len(layers[0]["gates"]), depth=len(layers),
             n_classes=head.k, tau=float(head.tau), seed=seed, layers=layers)
    with open(path, "w") as f:
        json.dump(d, f)
    return d
