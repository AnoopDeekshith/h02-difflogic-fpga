"""Train a DLGN, discretize it, and report the three-way baseline.

  soft acc   : relaxed network (softmax mixture of gates)
  hard acc   : discretized network in PyTorch (argmax gate per neuron)
  ref  acc   : NumPy bit-level golden model (must equal hard acc exactly)

Example (toy, ~1 min on CPU):
  python scripts/train.py --dataset digits --width 1000 --depth 4 --tau 10 \
      --epochs 60 --out runs/digits_w1000

MNIST, paper's "small" model (6 x 8000, tau = 10; GPU recommended):
  python scripts/train.py --dataset mnist --width 8000 --depth 6 --tau 10 \
      --epochs 100 --out runs/mnist_small

Power-aware stretch: add --act-weight 0.5 (sweep 0, 0.1, 0.3, 1, 3 ...).
"""
import argparse
import json
import os
import sys
import time

import numpy as np
import torch
import torch.nn.functional as F

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dlgn import data, hard                     # noqa: E402
from dlgn.model import DLGN                     # noqa: E402
from dlgn.gates import GATE_NAMES               # noqa: E402


def accuracy(model, x, y, bs=1000):
    model.eval()
    correct = 0
    with torch.no_grad():
        for i in range(0, len(x), bs):
            correct += (model(x[i:i+bs]).argmax(1) == y[i:i+bs]).sum().item()
    return correct / len(x)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="digits", choices=["digits", "mnist"])
    ap.add_argument("--pool", type=int, default=1, help="mnist only: 2 -> 14x14")
    ap.add_argument("--width", type=int, default=1000)
    ap.add_argument("--depth", type=int, default=4)
    ap.add_argument("--tau", type=float, default=10.0)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--bs", type=int, default=100)
    ap.add_argument("--lr", type=float, default=0.01)   # paper: Adam, 0.01
    ap.add_argument("--act-weight", type=float, default=0.0)
    ap.add_argument("--act-mode", default="batch", choices=["batch", "sample"])
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--out", default="runs/latest")
    args = ap.parse_args()

    torch.manual_seed(args.seed)
    kw = {"pool": args.pool} if args.dataset == "mnist" else {}
    xtr, ytr, xte, yte = data.get(args.dataset, **kw)
    dev = args.device
    Xtr, Ytr = torch.tensor(xtr, device=dev), torch.tensor(ytr, device=dev)
    Xte, Yte = torch.tensor(xte, device=dev), torch.tensor(yte, device=dev)
    n_classes = int(ytr.max()) + 1
    print(f"{args.dataset}: train {len(xtr)}, test {len(xte)}, {xtr.shape[1]} input bits")

    model = DLGN(xtr.shape[1], args.width, args.depth, n_classes,
                 args.tau, seed=args.seed).to(dev)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)

    t0 = time.time()
    for ep in range(1, args.epochs + 1):
        model.train()
        perm = torch.randperm(len(Xtr), device=dev)
        tot_ce = tot_act = 0.0
        for i in range(0, len(Xtr), args.bs):
            idx = perm[i:i+args.bs]
            ce = F.cross_entropy(model(Xtr[idx]), Ytr[idx])
            loss = ce
            if args.act_weight > 0:
                act = model.activity_penalty(args.act_mode)
                loss = loss + args.act_weight * act
                tot_act += act.item() * len(idx)
            opt.zero_grad()
            loss.backward()
            opt.step()
            tot_ce += ce.item() * len(idx)
        if ep == 1 or ep % 10 == 0 or ep == args.epochs:
            model.set_hard(False)
            sa = accuracy(model, Xte, Yte)
            model.set_hard(True)
            ha = accuracy(model, Xte, Yte)
            model.set_hard(False)
            msg = (f"ep {ep:3d}  ce {tot_ce/len(Xtr):.3f}  soft {sa:.4f}  "
                   f"hard {ha:.4f}  ({time.time()-t0:.0f}s)")
            if args.act_weight > 0:
                msg += f"  act {tot_act/len(Xtr):.3f}"
            print(msg, flush=True)

    # ---- three-way baseline ----
    os.makedirs(args.out, exist_ok=True)
    model.set_hard(False)
    soft_acc = accuracy(model, Xte, Yte)
    model.set_hard(True)
    hard_acc = accuracy(model, Xte, Yte)
    model.eval()
    with torch.no_grad():
        torch_scores = torch.cat([model(Xte[i:i+1000]) for i in range(0, len(Xte), 1000)])
    net = model.to_json(os.path.join(args.out, "model.json"))
    ref_scores = hard.scores(net, xte.astype(bool))
    ref_acc = float((ref_scores.argmax(1) == yte).mean())
    # torch hard scores are popcount / tau; must match the integer popcount
    match = np.allclose(torch_scores.cpu().numpy() * args.tau, ref_scores, atol=1e-3)
    act_ref = hard.toggle_rate(net, xte.astype(bool))
    gates = np.concatenate([l["gates"] for l in net["layers"]])
    hist = {GATE_NAMES[g]: int((gates == g).sum()) for g in range(16)}

    metrics = dict(args=vars(args), soft_acc=soft_acc, hard_acc=hard_acc,
                   ref_acc=ref_acc, discretization_gap=soft_acc - hard_acc,
                   torch_vs_ref_scores_match=bool(match),
                   ref_toggle_rate=float(act_ref), n_gates=int(gates.size),
                   gate_histogram=hist, train_seconds=time.time() - t0)
    with open(os.path.join(args.out, "metrics.json"), "w") as f:
        json.dump(metrics, f, indent=2)
    np.save(os.path.join(args.out, "x_test_bits.npy"), xte.astype(bool))
    np.save(os.path.join(args.out, "y_test.npy"), yte)

    print(f"\nsoft {soft_acc:.4f} | hard {hard_acc:.4f} | numpy ref {ref_acc:.4f} "
          f"| gap {100*(soft_acc-hard_acc):.2f} pts | torch==ref scores: {match}")
    print(f"zero-delay toggle rate per gate (test order): {act_ref:.3f}")
    print(f"saved {args.out}/model.json, metrics.json")
    if not match:
        sys.exit("ERROR: PyTorch hard model and NumPy reference disagree")


if __name__ == "__main__":
    main()
