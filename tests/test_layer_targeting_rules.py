"""Step 4.15 frozen selection and outcome rules."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import run_layer_targeting as rt  # noqa: E402


@pytest.mark.parametrize('control,correct,ok', [
    (248, 248, True), (248, 246, True),   # 0.74 pp
    (248, 245, False),                      # 1.11 pp (uniform lambda 0.3, seed 1)
    (249, 247, True), (253, 250, False),    # 2 images ok, 3 images = 1.11 pp fails
    (248, 250, True)])
def test_one_point_rule_on_270_images(control, correct, ok):
    assert rt.eligible(control, correct, 270) is ok


def cand(profile, lam, m1, correct):
    return {'profile': profile, 'lambda': lam, 'M1': m1, 'correct': correct}


def test_select_lowest_m1_among_eligible_targeted():
    c = [cand('L4', 0.3, 300, 240),          # ineligible despite lowest M1
         cand('L34', 0.1, 350, 247), cand('RAMP', 0.3, 340, 246), cand('U', 0.3, 330, 247)]
    assert rt.select(c, 248, 270, rt.PROFILE_ORDER)['profile'] == 'RAMP'
    assert rt.select(c, 248, 270, ('U',))['profile'] == 'U'


def test_select_ties_then_none():
    c = [cand('M23', 0.3, 340, 247), cand('L4', 0.3, 340, 247), cand('L34', 0.1, 340, 247),
         cand('RAMP', 0.1, 340, 248)]
    assert rt.select(c, 248, 270, rt.PROFILE_ORDER)['profile'] == 'RAMP'     # higher accuracy
    c = c[:3]
    assert rt.select(c, 248, 270, rt.PROFILE_ORDER)['profile'] == 'L34'      # lower lambda
    c = c[:2]
    assert rt.select(c, 248, 270, rt.PROFILE_ORDER)['profile'] == 'L4'       # profile order
    assert rt.select([cand('L4', 0.3, 1, 200)], 248, 270, rt.PROFILE_ORDER) is None


def row(ok, rt_, rc):
    return dict(target_eligible=ok, R_M1_target=rt_, R_M1_comparator=rc)


@pytest.mark.parametrize('rows,expected', [
    ([row(True, 0.08, 0.03)]*3, 'TARGETING_BETTER'),
    ([row(True, 0.08, 0.03)]*2 + [row(False, 0.08, 0.03)], 'TARGETING_NOT_SHOWN'),
    ([row(True, 0.08, 0.03)]*2 + [row(True, 0.019, 0.01)], 'TARGETING_NOT_SHOWN'),
    ([row(True, 0.08, 0.03)]*2 + [row(True, 0.03, 0.03)], 'TARGETING_NOT_SHOWN'),
    ([], 'TARGETING_NOT_SHOWN')])
def test_confirmation_outcome(rows, expected):
    assert rt.confirmation_outcome(rows) == expected


def test_frozen_policy_matches_runner():
    _, p = rt.load_policy(ROOT/'docs/experiments/layer-targeting-v1.json')
    assert tuple(p['targeted_profiles']) == rt.PROFILE_ORDER
    assert p['profiles']['U'] is None and p['lambdas'] == [0.1, 0.2, 0.3]
    assert p['discovery']['seed'] == 1 and p['confirmation']['seeds'] == [2, 3, 4]
    assert all(len(w) == 4 for k, w in p['profiles'].items() if k != 'U')
    with pytest.raises(ValueError):
        rt.load_policy(ROOT/'docs/experiments/hardware-switching-stop-rule-v3.json')


def test_label_names():
    assert rt.name('L4', 0.3) == 'L4_0p3' and rt.name('U', 0.1) == 'U_0p1'
