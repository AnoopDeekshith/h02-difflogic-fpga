"""Train fixed-budget models; use --defer-test for validation-only selection.

Example: python scripts/train.py --dataset digits --width 1000 --depth 4 \
    --tau 10 --epochs 60 --defer-test --out runs/digits_control_new
The saved historical runs/digits_w1000 must never be overwritten.
"""
import argparse
import json
from pathlib import Path
import platform
import sys
import time

import numpy as np
import torch
import torch.nn.functional as F

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dlgn import data, hard
from dlgn.model import DLGN
from dlgn.gates import GATE_NAMES
from dlgn.experiment import (SCHEMA, array_identity, hard_metrics, seal_run,
                             source_hashes, write_json, digest, validate_policy)


def accuracy(model, x, y, bs=1000):
    model.eval()
    correct = 0
    with torch.no_grad():
        for i in range(0, len(x), bs):
            correct += (model(x[i:i+bs]).argmax(1) == y[i:i+bs]).sum().item()
    return correct / len(x)


def raw_scores(model, x):
    model.eval()
    with torch.no_grad():
        return torch.cat([model(x[i:i+1000]) for i in range(0, len(x), 1000)]).cpu().numpy()


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--dataset', default='digits', choices=['digits', 'mnist'])
    ap.add_argument('--pool', type=int, default=1, help='mnist only: 2 -> 14x14')
    ap.add_argument('--width', type=int, default=1000)
    ap.add_argument('--depth', type=int, default=4)
    ap.add_argument('--tau', type=float, default=10.0)
    ap.add_argument('--epochs', type=int, default=60)
    ap.add_argument('--bs', type=int, default=100)
    ap.add_argument('--lr', type=float, default=0.01)
    ap.add_argument('--act-weight', type=float, default=0.0)
    ap.add_argument('--act-mode', default='batch', choices=['batch', 'sample'])
    ap.add_argument('--seed', type=int, default=0)
    ap.add_argument('--split-seed', type=int, default=0,
                    help='validation partition seed; separate from model initialization seed')
    ap.add_argument('--val-frac', type=float, default=0.2)
    ap.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    ap.add_argument('--defer-test', action='store_true',
                    help='do not evaluate or save test inputs/labels; select using validation only')
    ap.add_argument('--selection-policy', default=str(Path(__file__).resolve().parents[1] /
                    'docs/experiments/validation-selection-v1.json'),
                    help='policy copied into the run before training begins')
    ap.add_argument('--out', default='runs/latest', help='new output directory; existing directories are rejected')
    args = ap.parse_args(argv)
    if min(args.epochs, args.bs, args.depth, args.width, args.pool) < 1:
        ap.error('epochs, batch size, depth, width, and pooling must be positive')
    if not np.isfinite(args.tau) or args.tau <= 0 or not np.isfinite(args.lr) or args.lr <= 0:
        ap.error('tau and learning rate must be finite and positive')
    if not np.isfinite(args.act_weight) or args.act_weight < 0:
        ap.error('activity weight must be finite and nonnegative')
    if not np.isfinite(args.val_frac) or not 0 < args.val_frac < 1:
        ap.error('validation fraction must be finite and between zero and one')
    return args


def run(args):
    folder = Path(args.out)
    folder.mkdir(parents=True, exist_ok=False)
    write_json(folder / 'status.json', dict(status='running'))
    initial_sources = source_hashes()
    try:
        return train(args, folder, initial_sources)
    except Exception as exc:
        write_json(folder / 'status.json', dict(status='failed', error=f'{type(exc).__name__}: {exc}'))
        raise


def train(args, folder, initial_sources):
    import sklearn
    torch.manual_seed(args.seed)
    kw = {'pool': args.pool} if args.dataset == 'mnist' else {}
    xtr, ytr, xte, yte = data.get(args.dataset, **kw)
    train_idx, val_idx = data.validation_indices(len(xtr), ytr, args.val_frac, args.split_seed)
    xval, yval = xtr[val_idx], ytr[val_idx]
    xtr, ytr = xtr[train_idx], ytr[train_idx]
    dev = args.device
    Xtr, Ytr = torch.tensor(xtr, device=dev), torch.tensor(ytr, device=dev)
    Xval, Yval = torch.tensor(xval, device=dev), torch.tensor(yval, device=dev)
    n_classes = int(ytr.max()) + 1
    print(f'{args.dataset}: train {len(xtr)}, validation {len(xval)}, test {len(xte)}, {xtr.shape[1]} input bits')
    model = DLGN(xtr.shape[1], args.width, args.depth, n_classes, args.tau, seed=args.seed).to(dev)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    policy = json.loads(Path(args.selection_policy).read_text())
    validate_policy(policy)
    write_json(folder / 'selection_policy.json', policy)
    protocol = dict(schema=SCHEMA, args=vars(args), dataset_partition_seed=0,
                    selection_policy_sha256=digest(folder / 'selection_policy.json'),
                    train_inputs_identity=array_identity(xtr.astype(bool)),
                    train_labels_identity=array_identity(ytr),
                    validation_inputs_identity=array_identity(xval.astype(bool)),
                    validation_labels_identity=array_identity(yval),
                    split_identity=dict(train=array_identity(train_idx), validation=array_identity(val_idx)),
                    validation_order='unchanged saved validation indices into the training pool',
                    checkpoint_rule='final epoch of fixed training budget; no test-based selection',
                    versions=dict(python=platform.python_version(), numpy=np.__version__,
                                  torch=str(torch.__version__), sklearn=sklearn.__version__))
    write_json(folder / 'protocol.json', protocol)
    np.save(folder / 'x_validation_bits.npy', xval.astype(bool))
    np.save(folder / 'y_validation.npy', yval)
    np.savez(folder / 'split_indices.npz', train=train_idx, validation=val_idx)
    history = []
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
            sa = accuracy(model, Xval, Yval)
            model.set_hard(True)
            ha = accuracy(model, Xval, Yval)
            model.set_hard(False)
            history.append(dict(epoch=ep, validation_soft_acc=sa, validation_hard_acc=ha,
                                classification_loss=tot_ce/len(Xtr),
                                activity_term=tot_act/len(Xtr) if args.act_weight > 0 else None))
            print(f'ep {ep:3d}  ce {tot_ce/len(Xtr):.3f}  val_soft {sa:.4f}  val_hard {ha:.4f}', flush=True)

    model.set_hard(False)
    validation_soft_acc = accuracy(model, Xval, Yval)
    model.set_hard(True)
    validation_hard_acc = accuracy(model, Xval, Yval)
    val_torch_scores = raw_scores(model, Xval)
    net = model.to_json(folder / 'model.json')
    validation, val_scores, val_classes = hard_metrics(net, xval.astype(bool), yval)
    val_match = bool(np.allclose(val_torch_scores * args.tau, val_scores, atol=1e-3, rtol=0))
    val_class_match = bool(np.array_equal(val_torch_scores.argmax(1), val_classes))
    if not val_match or not val_class_match or validation_hard_acc != validation['ref_acc']:
        raise ValueError('Validation hard PyTorch scores/classes disagree with NumPy')
    np.save(folder / 'validation_scores.npy', val_scores)
    np.save(folder / 'validation_classes.npy', val_classes)

    # Deferred runs never construct test tensors, infer on test data, or save it.
    soft_acc = hard_acc = ref_acc = gap = match = act_ref = None
    if not args.defer_test:
        Xte, Yte = torch.tensor(xte, device=dev), torch.tensor(yte, device=dev)
        model.set_hard(False)
        soft_acc = accuracy(model, Xte, Yte)
        model.set_hard(True)
        hard_acc = accuracy(model, Xte, Yte)
        torch_scores = raw_scores(model, Xte)
        ref_scores = hard.scores(net, xte.astype(bool))
        ref_acc = float((ref_scores.argmax(1) == yte).mean())
        match = bool(np.allclose(torch_scores * args.tau, ref_scores, atol=1e-3, rtol=0)
                     and np.array_equal(torch_scores.argmax(1), ref_scores.argmax(1)))
        if not match:
            raise ValueError('Test hard PyTorch scores/classes disagree with NumPy')
        gap = soft_acc - hard_acc
        act_ref = float(hard.toggle_rate(net, xte.astype(bool)))
        np.save(folder / 'x_test_bits.npy', xte.astype(bool))
        np.save(folder / 'y_test.npy', yte)
    gates = np.concatenate([l['gates'] for l in net['layers']])
    hist = {GATE_NAMES[g]: int((gates == g).sum()) for g in range(16)}
    metrics = dict(args=vars(args), evaluation_protocol=SCHEMA, test_evaluated=not args.defer_test,
                   validation_soft_acc=validation_soft_acc, validation_hard_acc=validation_hard_acc,
                   validation=validation, validation_torch_vs_ref_scores_match=val_match,
                   validation_torch_vs_ref_classes_match=val_class_match, history=history,
                   n_train=len(xtr), n_validation=len(xval), n_test=len(xte),
                   soft_acc=soft_acc, hard_acc=hard_acc, ref_acc=ref_acc, discretization_gap=gap,
                   torch_vs_ref_scores_match=match, ref_toggle_rate=act_ref, n_gates=int(gates.size),
                   gate_histogram=hist, train_seconds=time.time() - t0)
    write_json(folder / 'metrics.json', metrics)
    model.set_hard(False)
    torch.save(dict(state_dict=model.state_dict(), optimizer_state_dict=opt.state_dict(),
                    torch_rng_state=torch.get_rng_state(), completed_epochs=args.epochs,
                    args=vars(args)), folder / 'checkpoint.pt')
    seal_run(folder, initial_sources)
    print(f"\nvalidation hard {validation_hard_acc:.4f} | NumPy scores/classes match | "
          f"settled toggle rate {validation['ref_toggle_rate']:.6f}")
    if args.defer_test:
        print('Test evaluation deferred; no test inputs/labels or metrics saved.')
    else:
        print(f'test soft {soft_acc:.4f} | hard {hard_acc:.4f} | numpy ref {ref_acc:.4f} | gap {100*gap:.2f} pts')
    print(f'saved {folder}/model.json, metrics.json')
    return metrics


def main():
    run(parse_args())


if __name__ == '__main__':
    main()
