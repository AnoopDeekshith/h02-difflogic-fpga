"""Step 4.15: optional per-layer weighting of the batch switching penalty."""
import sys
from pathlib import Path

import pytest
import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
from dlgn.model import DLGN  # noqa: E402
import train  # noqa: E402


@pytest.fixture
def model():
    torch.manual_seed(0)
    m = DLGN(16, 12, 4, 2, 10.0, seed=0)
    m(torch.rand(32, 16))
    return m


def per_layer(m):
    return [(2*l.last_out.mean(0)*(1-l.last_out.mean(0))).mean() for l in m.layers]


def test_default_is_unchanged_global_mean(model):
    expected = torch.cat([2*l.last_out.mean(0)*(1-l.last_out.mean(0)) for l in model.layers]).mean()
    assert torch.equal(model.activity_penalty('batch'), expected)


def test_equal_weights_match_global_mean_for_equal_widths(model):
    assert torch.allclose(model.activity_penalty('batch', [1, 1, 1, 1]), model.activity_penalty('batch'))


@pytest.mark.parametrize('weights', [[0, 0, 0, 1], [0, 0, 1, 1], [0, 1, 1, 0], [1, 2, 3, 4]])
def test_weighted_mean_of_layer_means(model, weights):
    terms = per_layer(model)
    expected = sum(w*t for w, t in zip(weights, terms)) / sum(weights)
    assert torch.allclose(model.activity_penalty('batch', weights), expected)


def test_last_layer_only_has_no_gradient_into_earlier_gate_choices_directly(model):
    # The last-layer term depends on earlier layers only through their outputs;
    # with weights [0,0,0,1] the value equals the last layer's own mean alpha.
    assert torch.allclose(model.activity_penalty('batch', [0, 0, 0, 1]), per_layer(model)[3])


@pytest.mark.parametrize('weights', [[1, 1, 1], [0, 0, 0, 0], [-1, 0, 0, 2], [0, 0, 0, float('nan')], [0, 0, 1, float('inf')]])
def test_invalid_weights_rejected(model, weights):
    with pytest.raises(ValueError):
        model.activity_penalty('batch', weights)


def test_cli_parses_and_validates(tmp_path):
    a = train.parse_args(['--act-weight', '0.3', '--act-layer-weights', '0,0,0,1', '--out', str(tmp_path/'x')])
    assert a.act_layer_weights == [0.0, 0.0, 0.0, 1.0]
    assert train.parse_args(['--out', str(tmp_path/'y')]).act_layer_weights is None
    for bad in (['--act-weight', '0.3', '--act-layer-weights', '0,0,1'],
                ['--act-weight', '0.3', '--act-layer-weights', '0,0,0,0'],
                ['--act-weight', '0.3', '--act-layer-weights', 'a,b,c,d'],
                ['--act-weight', '0', '--act-layer-weights', '0,0,0,1']):
        with pytest.raises(SystemExit):
            train.parse_args(bad + ['--out', str(tmp_path/'z')])
