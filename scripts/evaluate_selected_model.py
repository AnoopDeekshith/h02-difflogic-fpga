"""Evaluate a validation-selected checkpoint on test data without retraining."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dlgn import data, hard
from dlgn.model import DLGN
from dlgn.experiment import (array_identity, digest, read_validation_run,
                             select_validation, source_hashes, write_json)
from scripts.train import accuracy, raw_scores


def evaluate(selection_file, out):
    selection_file, out = Path(selection_file), Path(out)
    selection = json.loads(selection_file.read_text())
    if selection.get('schema') != 'validation_selection_v1':
        raise ValueError('Unsupported selection report')
    candidates = [r['directory'] for r in selection['candidates']
                  if r['directory'] != selection['control_directory']]
    checked = select_validation(selection['control_directory'], candidates, selection['policy'])
    if any(selection.get(k) != v for k, v in checked.items()):
        raise ValueError('Selection report does not reproduce from archived validation runs')
    run = read_validation_run(checked['selected_directory'])
    if source_hashes() != run['source_sha256']:
        raise ValueError('Use the archived training code before loading this checkpoint')
    args = run['metrics']['args']
    kw = {'pool': args['pool']} if args['dataset'] == 'mnist' else {}
    xpool, ypool, xte, yte = data.get(args['dataset'], **kw)
    ti, vi = data.validation_indices(len(xpool), ypool, args['val_frac'], args['split_seed'])
    identities = dict(train_inputs_identity=array_identity(xpool[ti].astype(bool)),
                      train_labels_identity=array_identity(ypool[ti]),
                      validation_inputs_identity=array_identity(xpool[vi].astype(bool)),
                      validation_labels_identity=array_identity(ypool[vi]),
                      split_identity=dict(train=array_identity(ti), validation=array_identity(vi)))
    if any(run['protocol'][k] != v for k, v in identities.items()):
        raise ValueError('Dataset regeneration differs from archived training/validation data')
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / 'status.json', dict(status='running'))
    try:
        folder = Path(run['directory'])
        checkpoint = torch.load(folder / 'checkpoint.pt', map_location='cpu', weights_only=True)
        if checkpoint['args'] != args:
            raise ValueError('Checkpoint configuration differs from selected run')
        net = hard.load(folder / 'model.json')
        model = DLGN(net['in_dim'], net['width'], net['depth'], net['n_classes'], net['tau'], seed=net['seed'])
        model.load_state_dict(checkpoint['state_dict'], strict=True)
        if model.to_json(out / 'model.json') != net:
            raise ValueError('Checkpoint gates/connections differ from selected hard model')
        x, y = torch.tensor(xte), torch.tensor(yte)
        model.set_hard(False)
        soft_acc = accuracy(model, x, y)
        model.set_hard(True)
        hard_acc = accuracy(model, x, y)
        torch_scores = raw_scores(model, x)
        ref_scores = hard.scores(net, xte.astype(bool))
        classes = ref_scores.argmax(1)
        score_match = bool(np.allclose(torch_scores * net['tau'], ref_scores, rtol=0, atol=1e-3))
        class_match = bool(np.array_equal(torch_scores.argmax(1), classes))
        if not score_match or not class_match:
            raise ValueError('Selected checkpoint test scores/classes disagree with NumPy')
        report = dict(schema='selected_test_evaluation_v1', selected_directory=run['directory'],
                      selection_sha256=digest(selection_file), selected_manifest_sha256=run['manifest_sha256'],
                      model_sha256=run['model_sha256'], n_test=len(xte), soft_acc=soft_acc,
                      hard_acc=hard_acc, ref_acc=float((classes == yte).mean()),
                      discretization_gap=soft_acc-hard_acc,
                      torch_vs_ref_scores_match=score_match, torch_vs_ref_classes_match=class_match,
                      ref_toggle_rate=float(hard.toggle_rate(net, xte.astype(bool))),
                      scope='Post-selection evaluation; digits test was historically inspected; not energy')
        np.save(out / 'x_test_bits.npy', xte.astype(bool))
        np.save(out / 'y_test.npy', yte)
        np.save(out / 'test_scores.npy', ref_scores)
        np.save(out / 'test_classes.npy', classes)
        write_json(out / 'metrics.json', report)
        files = ('model.json', 'metrics.json', 'x_test_bits.npy', 'y_test.npy',
                 'test_scores.npy', 'test_classes.npy')
        write_json(out / 'manifest.json', dict(files_sha256={name: digest(out/name) for name in files},
                                              evaluator_sha256=digest(Path(__file__))))
        write_json(out / 'status.json', dict(status='passed', manifest_sha256=digest(out / 'manifest.json')))
        return report
    except Exception as exc:
        write_json(out / 'status.json', dict(status='failed', error=f'{type(exc).__name__}: {exc}'))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True, help='new evaluation directory')
    args = parser.parse_args()
    result = evaluate(args.selection, args.out)
    print(f"Selected test hard accuracy {result['hard_acc']:.4f}; NumPy scores/classes match")


if __name__ == '__main__':
    main()
