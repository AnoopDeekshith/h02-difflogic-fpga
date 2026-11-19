"""Protocol checks: no test inference, reproducible selection, and archived evidence."""
import copy
import json
from pathlib import Path
import sys

import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dlgn import experiment as exp
from scripts import train
from scripts.evaluate_selected_model import evaluate


@pytest.fixture
def toy(monkeypatch):
    rng = np.random.default_rng(19)
    x = rng.integers(0, 2, (100, 6)).astype(np.float32)
    y = np.tile(np.array([0, 1], dtype=np.int64), 50)
    xt = rng.integers(0, 2, (12, 6)).astype(np.float32)
    yt = np.tile(np.array([0, 1], dtype=np.int64), 6)
    monkeypatch.setattr(train.data, 'get', lambda *a, **kw: (x, y, xt, yt))
    old = torch.get_num_threads()
    torch.set_num_threads(1)
    yield x, y, xt, yt
    torch.set_num_threads(old)


def make_run(tmp_path, name='control', weight=0, **changes):
    args = train.parse_args(['--width', '20', '--depth', '2', '--epochs', '1', '--bs', '20',
                             '--device', 'cpu', '--defer-test', '--act-weight', str(weight),
                             '--out', str(tmp_path/name)])
    for key, value in changes.items():
        setattr(args, key, value)
    train.run(args)
    return Path(args.out)


def policy():
    return json.loads((exp.ROOT/'docs/experiments/validation-selection-v1.json').read_text())


def test_deferred_mode_never_touches_test_arrays(tmp_path, toy, monkeypatch):
    class Forbidden:
        def __len__(self):
            return 12
        def __array__(self, *args, **kw):
            raise AssertionError('Test data was accessed during selection training')
        def __getitem__(self, key):
            raise AssertionError('Test data was indexed')
    x, y, _, _ = toy
    monkeypatch.setattr(train.data, 'get', lambda *a, **kw: (x, y, Forbidden(), Forbidden()))
    folder = make_run(tmp_path)
    result = exp.read_validation_run(folder)
    assert result['metrics']['test_evaluated'] is False
    assert result['metrics']['ref_acc'] is None
    assert not (folder/'x_test_bits.npy').exists()
    assert not (folder/'y_test.npy').exists()
    assert result['metrics']['validation']['opportunities'] == 40 * 19


def test_saved_order_counts_and_ties_use_independent_scalar_oracle(tmp_path, toy):
    folder = make_run(tmp_path)
    run = exp.read_validation_run(folder)
    net = json.loads((folder/'model.json').read_text())
    x = np.load(folder/'x_validation_bits.npy')
    states, scores = [], []
    for sample in x:
        h = [int(v) for v in sample]
        all_bits = []
        for layer in net['layers']:
            h = [int(f'{g:04b}'[2*h[a]+h[b]])
                 for a, b, g in zip(layer['ia'], layer['ib'], layer['gates'])]
            all_bits.extend(h)
        states.append(all_bits)
        scores.append([sum(h[:10]), sum(h[10:])])
    flips = sum(a != b for row1, row2 in zip(states, states[1:]) for a, b in zip(row1, row2))
    assert flips == run['metrics']['validation']['changes']
    assert np.array_equal(scores, np.load(folder/'validation_scores.npy'))
    tie_net = dict(n_classes=2, layers=[dict(ia=[0, 0], ib=[0, 0], gates=[15, 15])])
    _, tie_scores, tie_classes = exp.hard_metrics(tie_net, np.zeros((3, 1), bool), np.zeros(3, int))
    assert np.array_equal(tie_scores, np.ones((3, 2)))
    assert np.array_equal(tie_classes, np.zeros(3, int))


def test_repeated_seed_same_order_and_model_without_overwriting(tmp_path, toy):
    first, second = make_run(tmp_path, 'a'), make_run(tmp_path, 'b')
    a, b = exp.read_validation_run(first), exp.read_validation_run(second)
    assert a['model_sha256'] == b['model_sha256']
    assert a['protocol']['split_identity'] == b['protocol']['split_identity']
    assert a['metrics']['validation'] == b['metrics']['validation']
    before = exp.digest(first/'manifest.json')
    with pytest.raises(FileExistsError):
        make_run(tmp_path, 'a')
    assert exp.digest(first/'manifest.json') == before


@pytest.mark.parametrize('name', ['model.json', 'checkpoint.pt', 'x_validation_bits.npy',
                                 'split_indices.npz', 'metrics.json', 'selection_policy.json'])
def test_changed_archived_artifacts_are_rejected(tmp_path, toy, name):
    folder = make_run(tmp_path)
    with (folder/name).open('ab') as stream:
        stream.write(b'changed')
    with pytest.raises(ValueError, match='Changed training artifact'):
        exp.read_validation_run(folder)


def test_full_evaluation_mode_remains_available_but_is_not_a_candidate(tmp_path, toy):
    folder = make_run(tmp_path, defer_test=False)
    metrics = json.loads((folder/'metrics.json').read_text())
    assert metrics['test_evaluated'] is True
    assert metrics['hard_acc'] == metrics['ref_acc']
    assert (folder/'x_test_bits.npy').exists()
    with pytest.raises(ValueError, match='validation-only'):
        exp.read_validation_run(folder)


def test_failed_training_keeps_failed_status(tmp_path, toy, monkeypatch):
    def fail(*a, **kw):
        raise RuntimeError('deliberate injected failure')
    monkeypatch.setattr(train.data, 'get', fail)
    with pytest.raises(RuntimeError, match='injected'):
        make_run(tmp_path)
    assert json.loads((tmp_path/'control/status.json').read_text())['status'] == 'failed'


def test_real_selection_and_post_selection_evaluation_without_retraining(tmp_path, toy):
    control = make_run(tmp_path, 'control')
    candidate = make_run(tmp_path, 'candidate', weight=.1)
    selected = exp.select_validation(control, [candidate], policy())
    selection_path = tmp_path/'selection.json'
    exp.write_json(selection_path, selected)
    before = {str(p): exp.digest(p/'manifest.json') for p in (control, candidate)}
    report = evaluate(selection_path, tmp_path/'test_evaluation')
    assert report['torch_vs_ref_scores_match'] and report['torch_vs_ref_classes_match']
    assert report['n_test'] == 12
    assert before == {str(p): exp.digest(p/'manifest.json') for p in (control, candidate)}
    selected['selected_model_sha256'] = 'wrong'
    exp.write_json(selection_path, selected)
    with pytest.raises(ValueError, match='does not reproduce'):
        evaluate(selection_path, tmp_path/'tampered')
    assert not (tmp_path/'tampered').exists()


@pytest.mark.parametrize('changes', [dict(seed=2), dict(split_seed=1), dict(epochs=2), dict(lr=.02)])
def test_unmatched_runs_are_rejected(tmp_path, toy, changes):
    control = make_run(tmp_path, 'control')
    candidate = make_run(tmp_path, 'candidate', weight=.1, **changes)
    with pytest.raises(ValueError, match='Unmatched'):
        exp.select_validation(control, [candidate], policy())


def test_policy_must_be_frozen_before_training(tmp_path, toy):
    control = make_run(tmp_path)
    altered = policy()
    altered['max_accuracy_drop_pp'] = 2
    with pytest.raises(ValueError, match='before training'):
        exp.select_validation(control, [], altered)


def test_accuracy_budget_precedes_switching_and_control_can_win(tmp_path, monkeypatch):
    base = dict(metrics=dict(args=vars(train.parse_args([]))),
                protocol={k: 'same' for k in ('train_inputs_identity', 'train_labels_identity',
                          'validation_inputs_identity', 'validation_labels_identity', 'split_identity',
                          'versions', 'dataset_partition_seed')},
                source_sha256={'source': 'same'}, manifest_sha256='hash')
    records = {}
    for name, acc, switching, weight in [('control', .90, .30, 0), ('bad', .88, .01, .1),
                                         ('good', .90, .20, .2), ('better_acc', .91, .20, .3)]:
        folder = tmp_path/name
        folder.mkdir()
        exp.write_json(folder/'selection_policy.json', policy())
        item = copy.deepcopy(base)
        item.update(directory=str(folder), model_sha256=name)
        item['metrics']['args']['act_weight'] = weight
        item['metrics']['validation'] = dict(ref_acc=acc, ref_toggle_rate=switching)
        records[folder] = item
    monkeypatch.setattr(exp, 'read_validation_run', lambda folder: copy.deepcopy(records[Path(folder)]))
    result = exp.select_validation(tmp_path/'control', [tmp_path/n for n in ['bad', 'good', 'better_acc']], policy())
    assert result['selected_directory'] == str(tmp_path/'better_acc')
    assert next(r for r in result['candidates'] if r['act_weight'] == .1)['eligible'] is False
    records[tmp_path/'good']['metrics']['validation']['ref_toggle_rate'] = .31
    result = exp.select_validation(tmp_path/'control', [tmp_path/'good'], policy())
    assert result['selected_directory'] == str(tmp_path/'control')


@pytest.mark.parametrize('flag,value', [('--act-weight', 'nan'), ('--tau', '0'),
                                       ('--lr', 'inf'), ('--val-frac', 'nan'), ('--epochs', '0')])
def test_invalid_training_arguments_rejected_before_run(flag, value):
    with pytest.raises(SystemExit):
        train.parse_args([flag, value])
