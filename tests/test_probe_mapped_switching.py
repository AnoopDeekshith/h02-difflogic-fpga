"""Step 4.13 probe: fanout, core-net metrics and the frozen PAUSE/CONTINUE rule."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import probe_mapped_switching as probe  # noqa: E402


def entry(bit, category, driver, users):
    return dict(bit_id=bit, category=category, driver=driver, aliases=[], users=users)


LEDGER = dict(entries=[
    # primary input: excluded from core, its port reference is not load
    entry(2, 'data_input', 'primary:x[0]', ['port:x[0]', 'a:SB_LUT4.I0']),
    # LUT driving two LUT inputs and a top-level output port
    entry(3, 'lut', 'a:SB_LUT4.O', ['a:SB_LUT4.O', 'b:SB_LUT4.I1', 'c:SB_LUT4.I2', 'port:scores[0]']),
    # flip-flop driving one carry input
    entry(4, 'ff', 'f:SB_DFF.Q', ['f:SB_DFF.Q', 'k:SB_CARRY.I0']),
    # carry output with no load
    entry(5, 'carry', 'k:SB_CARRY.CO', ['k:SB_CARRY.CO']),
    entry(6, 'clock', 'primary:clk[0]', ['port:clk[0]', 'f:SB_DFF.C']),
])


def activity(toggles, unknown=None):
    unknown = unknown or [0]*len(toggles)
    return dict(per_bit=[dict(known_toggles=t, unknown_changes=u) for t, u in zip(toggles, unknown)])


def test_fanout_counts_only_cell_input_pins():
    assert [probe.fanout(e) for e in LEDGER['entries']] == [1, 2, 1, 0, 1]


def test_core_metrics_exclude_inputs_and_clock_and_weight_by_fanout():
    m = probe.core_metrics(LEDGER, activity([100, 10, 7, 5, 999]))
    assert m['core_nets'] == 3
    assert m['M1'] == 10 + 7 + 5
    assert m['M2'] == 10*2 + 7*1 + 5*0
    assert m['by_category']['lut'] == dict(nets=1, M1=10, M2=20)


def test_core_metrics_report_unknown_changes():
    assert probe.core_metrics(LEDGER, activity([0, 1, 1, 1, 0], [0, 2, 0, 0, 5]))['unknown_changes'] == 2


def test_width_mismatch_rejected():
    with pytest.raises(ValueError):
        probe.core_metrics(LEDGER, activity([1, 2]))


def test_unexpected_primary_load_rejected():
    bad = entry(9, 'lut', 'a:SB_LUT4.O', ['a:SB_LUT4.O', 'primary:x[1]'])
    with pytest.raises(ValueError):
        probe.fanout(bad)


@pytest.mark.parametrize('r1,r2,expected', [
    (0.0199, 0.0199, 'PAUSE'),
    (0.02, 0.0, 'CONTINUE'),      # exactly at threshold is not "below"
    (0.0, 0.02, 'CONTINUE'),
    (0.15, 0.01, 'CONTINUE'),     # one metric above suffices
    (-0.05, -0.01, 'PAUSE'),      # penalty switching more
])
def test_probe_decision(r1, r2, expected):
    assert probe.probe_decision(r1, r2, 2.0) == expected


def test_reduction_and_zero_control():
    assert probe.reduction(200, 150) == pytest.approx(0.25)
    assert probe.reduction(100, 120) == pytest.approx(-0.2)
    with pytest.raises(ValueError):
        probe.reduction(0, 5)


POLICIES = ROOT/'docs/experiments'
SEED1 = ROOT/'runs/step4.5-seeds.vyq2h2nf'


def test_only_frozen_v3_policy_is_accepted(tmp_path):
    path, policy = probe.load_policy(POLICIES/'hardware-switching-stop-rule-v3.json')
    assert policy['threshold_percent'] == 2.0
    for old in ('v1', 'v2'):
        with pytest.raises(ValueError):
            probe.load_policy(POLICIES/f'hardware-switching-stop-rule-{old}.json')
    edited = tmp_path/'v3.json'
    edited.write_text(path.read_text().replace('"threshold_percent": 2.0', '"threshold_percent": 1.0'))
    with pytest.raises(ValueError):
        probe.load_policy(edited)


def test_window_bounds_follow_step_3_8():
    assert probe.window_bounds(dict(first_input_ps=250003, last_output_check_ps=900000)) == (
        250003 - 41667 - 1, 900000)


@pytest.mark.skipif(not (SEED1/'seed_1_control').exists(), reason='archived step 4.5 runs absent')
def test_frozen_model_binding_and_run_checks():
    _, policy = probe.load_policy(POLICIES/'hardware-switching-stop-rule-v3.json')
    control, penalty = SEED1/'seed_1_control', SEED1/'seed_1_penalty'
    probe.check_frozen_models(policy, 1, control, penalty)
    with pytest.raises(ValueError):
        probe.check_frozen_models(policy, 1, penalty, control)   # swapped roles
    with pytest.raises(ValueError):
        probe.check_frozen_models(policy, 2, control, penalty)   # wrong seed
    probe.check_run(control, 0.0, 1)
    probe.check_run(penalty, 0.3, 1)
    with pytest.raises(ValueError):
        probe.check_run(penalty, 0.0, 1)                         # wrong lambda
    with pytest.raises(ValueError):
        probe.check_run(control, 0.0, 2)                         # wrong seed
