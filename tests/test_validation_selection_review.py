"""Independent checks for validation selection's scientific contracts."""
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
def workload(monkeypatch):
    rng = np.random.default_rng(410)
    x = rng.integers(0, 2, (80, 4)).astype(np.float32)
    y = np.tile(np.array([0, 1], dtype=np.int64), 40)
    xt = rng.integers(0, 2, (10, 4)).astype(np.float32)
    yt = np.tile(np.array([0, 1], dtype=np.int64), 5)
    monkeypatch.setattr(train.data, 'get', lambda *a, **kw: (x, y, xt, yt))
    old = torch.get_num_threads()
    torch.set_num_threads(1)
    yield
    torch.set_num_threads(old)


def make_run(tmp_path, name='control', *extra):
    args = train.parse_args(['--width', '8', '--depth', '2', '--epochs', '1',
                             '--bs', '16', '--device', 'cpu', '--defer-test',
                             '--out', str(tmp_path/name), *extra])
    train.run(args)
    return Path(args.out)


def policy():
    return json.loads((exp.ROOT/'docs/experiments/validation-selection-v1.json').read_text())


def reseal(folder):
    """Simulate a writer that hashes internally inconsistent reporting artifacts."""
    manifest = json.loads((folder/'manifest.json').read_text())
    exp.seal_run(folder, manifest['source_sha256'])


def test_fresh_numpy_recalculation_rejects_false_archived_accuracy(tmp_path, workload):
    folder = make_run(tmp_path)
    metrics = json.loads((folder/'metrics.json').read_text())
    metrics['validation']['ref_acc'] = 1 - metrics['validation']['ref_acc']
    if metrics['validation']['ref_acc'] == .5:
        metrics['validation']['ref_acc'] = .25
    exp.write_json(folder/'metrics.json', metrics)
    reseal(folder)
    with pytest.raises(ValueError, match='fresh NumPy'):
        exp.read_validation_run(folder)


def test_saved_integer_scores_are_verified_even_when_classes_unchanged(tmp_path, workload):
    folder = make_run(tmp_path)
    scores = np.load(folder/'validation_scores.npy')
    np.save(folder/'validation_scores.npy', scores + 1)
    reseal(folder)
    with pytest.raises(ValueError, match='validation scores disagree'):
        exp.read_validation_run(folder)


def test_order_identity_prevents_reordering_validation_without_protocol_update(tmp_path, workload):
    folder = make_run(tmp_path)
    x = np.load(folder/'x_validation_bits.npy')
    np.save(folder/'x_validation_bits.npy', x[::-1])
    reseal(folder)
    with pytest.raises(ValueError, match='identity mismatch'):
        exp.read_validation_run(folder)


def test_ablation_and_batch_penalty_are_separate_matched_protocols(tmp_path, workload):
    control = make_run(tmp_path)
    ablation = make_run(tmp_path, 'ablation', '--act-weight', '.1', '--act-mode', 'sample')
    with pytest.raises(ValueError, match='Unmatched'):
        exp.select_validation(control, [ablation], policy())


def test_duplicate_candidates_and_nonzero_control_rejected(tmp_path, workload):
    control = make_run(tmp_path)
    penalty = make_run(tmp_path, 'penalty', '--act-weight', '.1')
    with pytest.raises(ValueError, match='Duplicate'):
        exp.select_validation(control, [control], policy())
    with pytest.raises(ValueError, match='lambda zero'):
        exp.select_validation(penalty, [], policy())


def test_evaluation_only_loads_checkpoint_and_never_runs_optimizer(tmp_path, workload, monkeypatch):
    control = make_run(tmp_path)
    selected = exp.select_validation(control, [], policy())
    selection_file = tmp_path/'selection.json'
    exp.write_json(selection_file, selected)

    def forbid(*a, **kw):
        raise AssertionError('Post-selection evaluation must not train')

    monkeypatch.setattr(train, 'train', forbid)
    monkeypatch.setattr(torch.optim.Adam, 'step', forbid)
    result = evaluate(selection_file, tmp_path/'evaluation')
    assert result['n_test'] == 10
    assert result['torch_vs_ref_scores_match']
    assert result['torch_vs_ref_classes_match']
    assert exp.digest(control/'model.json') == result['model_sha256']
    with pytest.raises(FileExistsError):
        evaluate(selection_file, tmp_path/'evaluation')


def test_evaluator_rejects_changed_executable_sources(tmp_path, workload, monkeypatch):
    control = make_run(tmp_path)
    selection_file = tmp_path/'selection.json'
    exp.write_json(selection_file, exp.select_validation(control, [], policy()))
    import scripts.evaluate_selected_model as evaluator
    monkeypatch.setattr(evaluator, 'source_hashes', lambda: {'changed': 'source'})
    with pytest.raises(ValueError, match='archived training code'):
        evaluator.evaluate(selection_file, tmp_path/'evaluation')
    assert not (tmp_path/'evaluation').exists()
