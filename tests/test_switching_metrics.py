"""Step 3.10 complementary-metric checks."""
from itertools import permutations
import json
from pathlib import Path
import shutil
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import report_switching_metrics as rsm  # noqa: E402

MODEL_RUN = ROOT/'runs/digits_w1000'


def test_layer_view_counts_and_exact_random_order_expectation():
    h = np.array([[1, 0], [1, 1], [0, 1], [0, 0]], dtype=bool)
    v = rsm.layer_view(h, 50, np.random.default_rng(0))
    assert v['saved_order_changes'] == 3 and v['bit_pair_opportunities'] == 6
    assert v['surrogate_mean_2p1mp'] == 0.5
    brute = np.mean([rsm.adjacent_changes(h[list(p)]) for p in permutations(range(4))]) / 6
    assert v['random_order_expected_rate'] == pytest.approx(brute, abs=1e-15)
    assert v['random_order_expected_rate'] == pytest.approx(0.5 * 4/3)


def test_constant_bits_have_zero_surrogate_and_change():
    h = np.zeros((5, 3), dtype=bool)
    h[:, 1] = True
    v = rsm.layer_view(h, 10, np.random.default_rng(1))
    assert v['constant_bits'] == 3 and v['surrogate_mean_2p1mp'] == 0
    assert v['saved_order_changes'] == 0 and v['random_order_expected_rate'] == 0


def fake_timed():
    return dict(observed_net_bits=10, n_images=2,
                categories=dict(core=dict(nets=4, extra_per_settled=1.5)),
                totals=dict(nets=9, extra_per_settled=0.5))


@pytest.fixture
def results(tmp_path):
    if not (MODEL_RUN/'model.json').exists():
        pytest.skip('historical model run is not present')
    for step in ('3.6', '3.7', '3.8'):
        shutil.copyfile(rsm.RESULTS/rsm.TRACKED[step], tmp_path/rsm.TRACKED[step])
    (tmp_path/rsm.TRACKED['3.9']).write_text(json.dumps(fake_timed()))
    return tmp_path


def test_report_reproduces_tracked_layer_counts(results):
    out = rsm.report(MODEL_RUN, permutations=20, results=results)
    layers = out['logical']['layers']
    assert [layers[f'l{i}']['saved_order_changes'] for i in range(1, 5)] == [126546, 144016, 167436, 190171]
    assert out['logical']['all_gates']['saved_order_rate'] == pytest.approx(628169/1796000, abs=1e-15)
    assert out['logical']['input_bits']['saved_order_changes'] == 22013
    assert {row['source'] for row in out['table']} >= {'3.6', '3.7 (RTL = NumPy)', '3.8', '3.9'}


@pytest.mark.parametrize('fault', ['layer', 'total', 'input'])
def test_report_rejects_tampered_tracked_results(results, fault):
    path = results/rsm.TRACKED['3.7']
    data = json.loads(path.read_text())
    if fault == 'layer':
        next(o for o in data['observations'] if o['signal'] == 'l2_c')['rtl']['known_bit_toggles'] += 1
    elif fault == 'total':
        data['logical_gate_output_metric']['known_bit_toggles'] -= 1
    else:
        next(o for o in data['observations'] if o['signal'] == 'x')['rtl']['known_bit_toggles'] += 2
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        rsm.report(MODEL_RUN, permutations=5, results=results)
