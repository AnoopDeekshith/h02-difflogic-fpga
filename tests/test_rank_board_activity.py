"""Step 4.11 board-activity ranking: block rules and the verified step 3.9 figures."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import rank_board_activity as rank  # noqa: E402

CAPTURE = ROOT/'runs/step3.9-glitch/timed-activity.0hvnej44'


def e(driver, category, names):
    return dict(driver=driver, category=category, names=names)


@pytest.mark.parametrize('entry,expected', [
    (e('c5.GLOBAL_BUFFER_OUTPUT', 'clock', ['clk$SB_IO_IN_$glb_clk']), 'clock'),
    (e('c1.O', 'core', ['board.adapter.core.sc_flat[3]']), 'core'),
    (e('c2.Q', 'interface', ['board.adapter.idle_count[4]']), 'idle_count.register'),
    (e('c3.O', 'interface', ['board.adapter.idle_count_SB_DFFSR_Q_19_D_SB_LUT4_O_I3']), 'idle_count.next_state_logic'),
    (e('c4.Q', 'interface', ['board.adapter.receiver.timer[2]']), 'rx_timer.register'),
    (e('c7.Q', 'interface', ['board.adapter.transmitter.timer[0]']), 'tx_timer.register'),
    (e('c8.O', 'interface', ['board.adapter.receiver.state[1]']), 'rx_other'),
    (e('c9.O', 'unclassified', ['$nextpnr_ICESTORM_LC_9$O']), 'unclassified'),
])
def test_block_rules(entry, expected):
    assert rank.block(entry) == expected


def test_overrides_take_precedence():
    entry = e('c4006.O', 'interface', ['board.adapter.receiver.state_SB_DFF_Q_D_SB_LUT4_O_I3_SB_LUT4_O_I3[0]'])
    assert rank.block(entry) == 'rx_other'
    assert rank.block(entry, rank.OVERRIDES) == 'rx_timer.register'


@pytest.mark.skipif(not (CAPTURE/'net-ledger.json').exists(), reason='step 3.9 capture absent')
def test_verified_step_3_9_figures():
    r = rank.rank(CAPTURE)
    s = r['summary']
    assert r['total_timed_transitions'] == 4789099
    assert r['total_with_clock_once'] == 4789099 - 651360
    assert len(r['overrides_applied']) == 6
    assert s['counters'] == {'idle_count': 1234400, 'rx_timer': 1397760, 'tx_timer': 653149}
    assert round(100*s['clock_share'], 1) == 27.2
    assert round(100*s['core_share'], 2) == 0.68
    assert round(100*s['counter_register_share'], 2) == 21.66
    blocks = {b['block']: b for b in r['blocks']}
    assert blocks['core']['timed'] == 32580 and blocks['core']['settled'] == 12178
