"""Independent category, settled endpoint and raw-event checks for step 3.6."""
from bisect import bisect_right
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from report_activity_categories import report_categories, partition_activity  # noqa: E402
from test_activity_windows import make_capture, refresh_hash, inject_value, trace_values  # noqa: E402
from test_vcd_activity import string_oracle  # noqa: E402


def independent_role(alias, params):
    """Separate expected role table; do not consult production categorizer."""
    parts, name = alias['scope'], alias['reference']
    if parts == ['tb_capture']:
        return 'testbench'
    if len(parts) == 3:
        assert parts[2].startswith('$ivl_for_loop') and name == 'k'
        return 'simulator_bookkeeping'
    assert parts == ['tb_capture', 'dut']
    if name in ['clk']:
        return 'clock'
    if name in ['rst', 'in_valid', 'out_valid', 'vpipe']:
        return 'control'
    if name == 'x':
        return 'input_port'
    if name in ['l0', 'scores', 'class_out']:
        return 'data_register'
    if name in [f'l{i}_c' for i in range(1, params['D']+1)]:
        return 'logical_layer_output'
    if name in [f'l{i}' for i in range(1, params['D']+1)]:
        return 'layer_register' if params['LAT']-int(params['head_pipeline']) > 2 else 'logical_layer_copy'
    if name == 'sc_flat' and params['head_pipeline']:
        return 'head_score_register_view'
    if name in ['best', 'best_sc', 'sc_flat'] or name.startswith(('pc', 'win_')):
        return 'output_logic'
    assert name == 'LATENCY', name
    return 'elaboration_constant'


def assert_report_oracle(report):
    """Independent line decoder and per-bit oracle for a passed report."""
    capture = Path(report['capture_directory'])
    vcd = capture/'dlgn.vcd'
    declaration, snapshots = trace_values(vcd)
    times = sorted(snapshots)
    raw = string_oracle(vcd)
    mapping = {'known': 'known_bit_toggles', 'rises': 'rises', 'falls': 'falls',
               'unknown_changes': 'unknown_bit_changes', 'state_changes': 'four_state_bit_changes'}
    partition = report['whole_trace']
    assert partition['unique_identifier_count'] == len(raw)
    assert partition['declaration_count'] == len(declaration)
    assert {r['identifier'] for r in partition['signals']} == raw.keys()
    for row in partition['signals']:
        for declared in row['aliases']:
            path = '.'.join(declared['scope']+[declared['reference']])
            assert declaration[path] == (row['identifier'],row['width'])
        roles = {independent_role(a, report['architecture']) for a in row['aliases']}
        roles.discard('testbench') if len(roles) > 1 else None
        if roles == {'logical_layer_output', 'logical_layer_copy'}:
            roles.remove('logical_layer_copy')
        assert roles == {row['category']}
        for source, target in mapping.items():
            assert raw[row['identifier']][source] == row['counts'][target]
    for category, values in partition['categories'].items():
        members = [r for r in partition['signals'] if r['category'] == category]
        assert len(members) == values['identifier_count']
        assert sum(r['width'] for r in members) == values['declared_bits']
        for key, total in values['counts'].items():
            assert sum(r['counts'][key] for r in members) == total
    for key, total in partition['totals'].items():
        assert sum(c['counts'][key] for c in partition['categories'].values()) == total
    event_windows = {}
    for row in report['observations']:
        path = 'tb_capture.dut.'+row['signal']
        identifier, width = declaration[path]
        assert (identifier, width) == (row['identifier'], row['width'])
        sample_times = [row['first_sample_ps']+i*report['clock']['simulated_period_ps']
                        for i in range(report['n_images'])]
        values = [snapshots[times[bisect_right(times,t)-1]][path] for t in sample_times]
        assert all(v is not None for v in values)
        flips = rises = falls = 0
        for before, after in zip(values, values[1:]):
            flips += sum(a != b for a,b in zip(f'{before:0{width}b}', f'{after:0{width}b}'))
            rises += sum(a == '0' and b == '1' for a,b in zip(f'{before:0{width}b}', f'{after:0{width}b}'))
            falls += sum(a == '1' and b == '0' for a,b in zip(f'{before:0{width}b}', f'{after:0{width}b}'))
        assert row['settled'] == dict(known_bit_toggles=flips, rises=rises, falls=falls,
            bit_pair_opportunities=width*(len(values)-1),
            changes_per_bit_per_image_pair=flips/(width*(len(values)-1)))
        bounds = (row['start_exclusive_tick'], row['end_inclusive_tick'])
        if bounds not in event_windows:
            event_windows[bounds] = string_oracle(vcd, *bounds)
        for source, target in mapping.items():
            assert event_windows[bounds][identifier][source] == row['recorded'][target]
    canonical = [r for r in report['observations'] if r['signal'] in
                 [f'l{i}_c' for i in range(1,report['architecture']['D']+1)]]
    metric = report['logical_gate_output_metric']
    assert metric['signals'] == [r['signal'] for r in canonical]
    assert metric['known_bit_toggles'] == sum(r['settled']['known_bit_toggles'] for r in canonical)
    assert metric['bit_pair_opportunities'] == sum(r['width']*(report['n_images']-1) for r in canonical)
    assert metric['adjacent_image_pairs'] == report['n_images']-1
    assert metric['changes_per_gate_per_image_pair'] == metric['known_bit_toggles']/metric['bit_pair_opportunities']
    return dict(identifiers=len(raw), observations=len(report['observations']),
                category_partition_and_raw_oracle=True, settled_endpoint_oracle=True)


@pytest.mark.parametrize('pipeline,head', [(False,False),(False,True),(True,False),(True,True)])
def test_all_architectures_match_independent_raw_and_settled_oracles(tmp_path,pipeline,head):
    make_capture(tmp_path,pipeline=pipeline,head=head)
    result = report_categories(tmp_path)
    assert_report_oracle(result)
    roles = {r['signal']:r['role'] for r in result['observations']}
    assert roles['l1'] == ('layer_register' if pipeline else 'logical_layer_copy')
    assert roles['sc_flat'] == ('head_score_register_view' if head else 'output_logic')
    assert 'layer_register' in result['whole_trace']['categories'] if pipeline else 'layer_register' not in result['whole_trace']['categories']


def test_repeated_frames_have_zero_settled_data_activity(tmp_path):
    make_capture(tmp_path,repeated=True)
    result = report_categories(tmp_path)
    assert_report_oracle(result)
    assert all(r['settled']['known_bit_toggles'] == 0 for r in result['observations'])
    assert result['whole_trace']['categories']['clock']['counts']['known_bit_toggles'] > 0
    assert result['logical_gate_output_metric']['bit_pair_opportunities'] == 24*3*15


@pytest.mark.parametrize('unknown', [False,True])
def test_intermediate_events_remain_separate_from_settled_changes(tmp_path,unknown):
    manifest = make_capture(tmp_path)
    before = report_categories(tmp_path)
    t = manifest['events']['first_input_ps']+100
    path = 'tb_capture.dut.l1_c'
    _, snapshots = trace_values(tmp_path/'dlgn.vcd')
    current = snapshots[max(s for s in snapshots if s <= t)][path]
    inject_value(tmp_path,path,t,'x' if unknown else format(current^1,'b'))
    inject_value(tmp_path,path,t+1,format(current,'b'))
    after = report_categories(tmp_path)
    assert_report_oracle(after)
    assert before['logical_gate_output_metric'] == after['logical_gate_output_metric']
    first = next(r for r in before['observations'] if r['signal'] == 'l1_c')
    second = next(r for r in after['observations'] if r['signal'] == 'l1_c')
    if unknown:
        assert second['recorded']['unknown_bit_changes'] == first['recorded']['unknown_bit_changes']+48
    else:
        assert second['recorded']['known_bit_toggles'] == first['recorded']['known_bit_toggles']+2


def fake_analysis(aliases):
    fields = ('observed_records','initializations','initial_unknown_bits','value_change_records',
              'redundant_value_records','known_bit_toggles','rises','falls','unknown_bit_changes',
              'four_state_bit_changes','unknown_value_records')
    counts = {key:0 for key in fields}
    counts.update(known_bit_toggles=2, rises=1, falls=1)
    rows = [dict(identifier=str(i),width=4,aliases=a,counts=counts.copy()) for i,a in enumerate(aliases)]
    return dict(signals=rows,totals={k:len(rows)*v for k,v in counts.items()},
                unique_identifier_count=len(rows),declaration_count=sum(map(len,aliases)),
                window=dict(start_exclusive_tick=None,end_inclusive_tick=None))


def alias(name,scope=None):
    scope = ['tb_capture','dut'] if scope is None else scope
    return dict(scope=scope,reference=name,path='.'.join(scope+[name]))


@pytest.mark.parametrize('names,owner', [(['l1_c','l1'],'logical_layer_output'),
                                       (['clk','clk_tb'],'clock')])
def test_true_aliases_are_counted_once(names,owner):
    aliases = [alias(names[0]),alias(names[1],['tb_capture'] if owner=='clock' else None)]
    r = partition_activity(fake_analysis([aliases]),dict(D=3,LAT=3,head_pipeline=True))
    assert r['unique_identifier_count'] == 1 and r['declaration_count'] == 2
    assert r['categories'][owner]['counts']['known_bit_toggles'] == 2


def test_equal_records_on_distinct_ids_are_not_implicitly_aliased():
    r = partition_activity(fake_analysis([[alias('l1_c')],[alias('l1')]]),dict(D=3,LAT=3,head_pipeline=True))
    assert r['unique_identifier_count'] == 2
    assert r['categories']['logical_layer_output']['counts']['known_bit_toggles'] == 2
    assert r['categories']['logical_layer_copy']['counts']['known_bit_toggles'] == 2


@pytest.mark.parametrize('names,pipeline', [(['clk','l0'],False),(['l1_c','l1'],True)])
def test_ambiguous_cross_category_aliases_are_rejected(names,pipeline):
    with pytest.raises(ValueError,match='Ambiguous'):
        partition_activity(fake_analysis([[alias(n) for n in names]]),dict(D=3,LAT=6 if pipeline else 3,head_pipeline=True))


@pytest.mark.parametrize('bad_alias', [alias('unknown'),alias('k',['tb_capture','dut','unexpected']),alias('clk',['other'])])
def test_unclassified_observations_are_rejected(bad_alias):
    with pytest.raises(ValueError,match='Unclassified'):
        partition_activity(fake_analysis([[bad_alias]]),dict(D=3,LAT=3,head_pipeline=True))


@pytest.mark.parametrize('fault', ['hash','rtl','missing_hash','unknown_signal','ledger'])
def test_bad_capture_is_rejected_and_failed_attempt_preserved(tmp_path,fault):
    make_capture(tmp_path)
    if fault in ('hash','rtl'):
        p=tmp_path/'dlgn_top.sv'
        p.write_text(p.read_text()+'// modified export\n')
        if fault == 'rtl':
            refresh_hash(tmp_path,'dlgn_top.sv')
    elif fault == 'missing_hash':
        p=tmp_path/'result.json'
        manifest=json.loads(p.read_text())
        del manifest['files_sha256']['events.csv']
        p.write_text(json.dumps(manifest))
    elif fault == 'unknown_signal':
        p=tmp_path/'dlgn.vcd'
        p.write_text(p.read_text().replace(' best ', ' mystery '))
        refresh_hash(tmp_path,'dlgn.vcd')
    else:
        p=tmp_path/'events.csv'
        p.write_text(p.read_text().replace('input,0,291669,4','input,0,291670,4'))
        refresh_hash(tmp_path,'events.csv')
    with pytest.raises(ValueError):
        report_categories(tmp_path)
    saved=list(tmp_path.glob('activity-categories.*/result.json'))
    assert len(saved)==1 and json.loads(saved[0].read_text())['status']=='failed'
