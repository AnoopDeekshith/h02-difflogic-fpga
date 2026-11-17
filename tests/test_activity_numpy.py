"""Independent scalar-reference and line-decoded checks of step 3.7."""
from bisect import bisect_right
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from compare_activity_numpy import compare_activity, pack_bits  # noqa: E402
from dlgn.export_verilog import emit_rtl, write_vectors  # noqa: E402
from test_activity_windows import make_capture, refresh_hash, inject_value, trace_values  # noqa: E402
from test_vcd_activity import string_oracle  # noqa: E402


def scalar_reference(capture):
    """Scalar truth-table evaluation and explicit numbered-bit packing.

    No hard.forward_bits/scores/predict, production packing or VCD parser.
    """
    capture = Path(capture)
    net = json.loads((capture/'model.json').read_text())
    inputs = np.load(capture/'x_test_bits.npy', allow_pickle=False)
    params = json.loads((capture/'params.json').read_text())
    refs = {name: [] for name in ['x', 'l0', 'sc_flat', 'scores', 'best', 'class_out']}
    for d in range(1, len(net['layers'])+1):
        refs[f'l{d}'] = []
        refs[f'l{d}_c'] = []
    tied = 0
    for image in inputs:
        bits = [int(v) for v in image]
        word = sum(v*2**j for j, v in enumerate(bits))
        refs['x'].append(word)
        refs['l0'].append(word)
        for d, layer in enumerate(net['layers'], 1):
            following = []
            for a, b, gate in zip(layer['ia'], layer['ib'], layer['gates']):
                truth_table = f'{gate:04b}'
                following.append(int(truth_table[2*bits[a]+bits[b]]))
            bits = following
            word = sum(v*2**j for j, v in enumerate(bits))
            refs[f'l{d}'].append(word)
            refs[f'l{d}_c'].append(word)
        group = len(bits)//net['n_classes']
        scores = [sum(bits[k*group:(k+1)*group]) for k in range(net['n_classes'])]
        largest = max(scores)
        tied += scores.count(largest) > 1
        winner = scores.index(largest)
        packed = sum(v*2**(k*params['SW']) for k, v in enumerate(scores))
        for name in ('sc_flat', 'scores'):
            refs[name].append(packed)
        for name in ('best', 'class_out'):
            refs[name].append(winner)
    return refs, tied


def assert_numpy_report_oracle(report):
    """Audit sampled values, pair masks, bit counts, raw counts and provenance."""
    capture, out = Path(report['capture_directory']), Path(report['directory'])
    refs, tied = scalar_reference(capture)
    declarations, snapshots = trace_values(capture/'dlgn.vcd')
    times = sorted(snapshots)
    archived = json.loads((out/'settled-values.json').read_text())
    assert report['checks']['tied_score_images'] == tied
    assert report['checks']['tie_breaking'] == 'lowest class index'
    assert report['checks']['all_observation_values_and_transition_masks_match']
    assert report['mismatch_count'] == 0
    assert report['matched_observations'] == len(report['observations'])
    assert len(archived) == len(report['observations'])
    event_windows = {}
    canonical_flips = canonical_opportunities = canonical_rises = canonical_falls = 0
    for row, evidence in zip(report['observations'], archived):
        name, width = row['signal'], row['width']
        path = 'tb_capture.dut.'+name
        assert declarations[path] == (row['identifier'], width)
        sample_times = [row['first_sample_ps']+i*report['clock']['simulated_period_ps']
                        for i in range(report['n_images'])]
        values = [snapshots[times[bisect_right(times,t)-1]][path] for t in sample_times]
        assert values == refs[name]
        assert evidence == dict(signal=name, width=width, sample_times_ps=sample_times,
                                numpy_hex=[format(v,'x') for v in refs[name]],
                                rtl_hex=[format(v,'x') for v in values])
        changes = [0]*width
        rises = falls = 0
        for actual_before, actual_after, expected_before, expected_after in zip(
                values,values[1:],refs[name],refs[name][1:]):
            for j in range(width):
                a, b = (actual_before//2**j)%2, (actual_after//2**j)%2
                e, f = (expected_before//2**j)%2, (expected_after//2**j)%2
                assert (a,b) == (e,f)
                assert (a != b) == (e != f)
                changes[j] += a != b
                rises += a == 0 and b == 1
                falls += a == 1 and b == 0
        stats = dict(known_bit_toggles=sum(changes),rises=rises,falls=falls,
                     bit_pair_opportunities=width*(len(values)-1),
                     changes_per_bit_per_image_pair=sum(changes)/(width*(len(values)-1)))
        assert row['rtl'] == row['numpy'] == stats
        assert row['mismatched_samples'] == row['mismatched_sample_bits'] == 0
        assert row['mismatched_transition_pairs'] == row['mismatched_transition_bits'] == 0
        assert row['first_mismatches'] == []
        canonical = name in [f'l{d}_c' for d in range(1,report['architecture']['D']+1)]
        assert row['canonical_logical_output'] == canonical
        if canonical:
            assert row['per_gate_numpy_changes'] == row['per_gate_rtl_changes'] == changes
            canonical_flips += sum(changes)
            canonical_opportunities += width*(len(values)-1)
            canonical_rises += rises
            canonical_falls += falls
        bounds = row['start_exclusive_tick'],row['end_inclusive_tick']
        if bounds not in event_windows:
            event_windows[bounds] = string_oracle(capture/'dlgn.vcd', *bounds)
        raw = event_windows[bounds][row['identifier']]
        for origin,target in [('known','known_bit_toggles'),('rises','rises'),('falls','falls'),
                              ('unknown_changes','unknown_bit_changes'),('state_changes','four_state_bit_changes')]:
            assert raw[origin] == row['recorded'][target]
        assert row['recorded_minus_settled_known_changes'] == raw['known']-sum(changes)
    assert report['logical_gate_output_metric'] == dict(known_bit_toggles=canonical_flips,
        rises=canonical_rises,falls=canonical_falls,bit_pair_opportunities=canonical_opportunities,
        changes_per_gate_per_image_pair=canonical_flips/canonical_opportunities)
    assert report['compared_sample_bits'] == sum(r['width']*report['n_images'] for r in report['observations'])
    assert report['compared_transition_bits'] == sum(r['width']*(report['n_images']-1) for r in report['observations'])
    sha = lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    assert sha(capture/'result.json') == report['capture_report_sha256']
    assert (capture/'result.json').read_bytes() == (out/'capture-manifest.json').read_bytes()
    for name,h in report['capture_artifacts_sha256'].items():
        assert sha(capture/name) == h
    for name,h in report['analysis_artifacts_sha256'].items():
        assert sha(out/name) == h
    for name,h in report['source_sha256'].items():
        assert sha(name) == h
    return dict(observations=len(report['observations']), scalar_gate_reference=True,
                exact_sample_and_transition_bit_oracle=True, raw_event_oracle=True,
                capture_artifacts_verified=len(report['capture_artifacts_sha256']),
                analysis_artifacts_verified=len(report['analysis_artifacts_sha256']),
                source_hashes_verified=len(report['source_sha256']))


@pytest.mark.parametrize('pipeline,head',[(False,False),(False,True),(True,False),(True,True)])
def test_all_register_architectures_match_scalar_and_vcd_oracles(tmp_path,pipeline,head):
    make_capture(tmp_path,pipeline=pipeline,head=head)
    result = compare_activity(tmp_path)
    assert_numpy_report_oracle(result)


def test_numbered_bits_across_byte_boundaries_keep_their_position():
    rows = np.zeros((6,17),dtype=bool)
    positions = [0,7,8,9,15,16]
    for row, bit in zip(rows,positions):
        row[bit] = True
    assert pack_bits(rows) == [1,128,256,512,32768,65536]


def test_repeated_zero_images_keep_zero_changes(tmp_path):
    make_capture(tmp_path,repeated=True)
    result = compare_activity(tmp_path)
    assert_numpy_report_oracle(result)
    assert result['logical_gate_output_metric']['known_bit_toggles'] == 0
    assert result['logical_gate_output_metric']['bit_pair_opportunities'] == 3*24*15


def test_deliberately_tied_scores_choose_lowest_class(tmp_path):
    original = tmp_path/'original'
    manifest = make_capture(original)
    folder = tmp_path/'tied'
    shutil.copytree(original,folder)
    net = json.loads((folder/'model.json').read_text())
    net['layers'][-1]['gates'] = [0]*24
    (folder/'model.json').write_text(json.dumps(net))
    rtl,params = emit_rtl(net,pipeline=False,head_pipeline=True)
    (folder/'dlgn_top.sv').write_text(rtl)
    write_vectors(net,np.load(folder/'x_test_bits.npy'),folder,params)
    commands = json.loads((folder/'commands.json').read_text())
    for name,command in zip(('build.log','sim.log'),commands):
        run = subprocess.run(command,cwd=folder,capture_output=True,text=True,timeout=30)
        (folder/name).write_text(run.stdout+run.stderr)
        assert run.returncode == 0,run.stdout+run.stderr
    manifest['files_sha256'] = {name:hashlib.sha256((folder/name).read_bytes()).hexdigest()
                               for name in manifest['files_sha256']}
    (folder/'result.json').write_text(json.dumps(manifest))
    result = compare_activity(folder)
    assert_numpy_report_oracle(result)
    assert result['checks']['tied_score_images'] == 16
    refs,_ = scalar_reference(folder)
    assert refs['scores'] == refs['class_out'] == [0]*16


def failed_result(folder):
    reports = [json.loads(p.read_text()) for p in Path(folder).glob('activity-numpy.*/result.json')]
    assert len(reports) == 1 and reports[0]['status'] == 'failed'
    return reports[0]


def at_value(folder,name,timestamp):
    _,snapshots = trace_values(Path(folder)/'dlgn.vcd')
    return snapshots[max(t for t in snapshots if t <= timestamp)]['tb_capture.dut.'+name]


def test_wrong_layer_states_with_same_total_toggle_count_are_rejected(tmp_path):
    manifest = make_capture(tmp_path)
    first = manifest['events']['first_input_ps']+1
    values = [(first+i*83334,at_value(tmp_path,'l1_c',first+i*83334)) for i in range(16)]
    for t,value in values:
        inject_value(tmp_path,'tb_capture.dut.l1_c',t,format(value^1,'b'))
        inject_value(tmp_path,'tb_capture.dut.l1_c',t+1,format(value,'b'))
    with pytest.raises(ValueError,match='settled value mismatch'):
        compare_activity(tmp_path)
    report = failed_result(tmp_path)
    layer = next(r for r in report['observations'] if r['signal']=='l1_c')
    assert layer['mismatched_samples'] == layer['mismatched_sample_bits'] == 16
    assert layer['mismatched_transition_pairs'] == 0
    assert layer['rtl']['known_bit_toggles'] == layer['numpy']['known_bit_toggles']
    assert layer['first_mismatches'][0]['differing_bit_indices'] == [0]
    assert (Path(report['directory'])/'settled-values.json').exists()


@pytest.mark.parametrize('pipeline',[False,True])
def test_copy_or_register_value_mismatch_is_not_hidden_by_canonical_match(tmp_path,pipeline):
    manifest = make_capture(tmp_path,pipeline=pipeline)
    t = manifest['events']['first_input_ps']+1+(83334 if pipeline else 0)
    value = at_value(tmp_path,'l1',t)
    inject_value(tmp_path,'tb_capture.dut.l1',t,format(value^1,'b'))
    inject_value(tmp_path,'tb_capture.dut.l1',t+1,format(value,'b'))
    with pytest.raises(ValueError,match='settled value mismatch'):
        compare_activity(tmp_path)
    row = next(r for r in failed_result(tmp_path)['observations'] if r['signal']=='l1')
    assert row['mismatched_samples'] == row['mismatched_transition_pairs'] == 1


@pytest.mark.parametrize('unknown',[False,True])
def test_intermediate_events_do_not_change_settled_comparison(tmp_path,unknown):
    manifest = make_capture(tmp_path)
    t = manifest['events']['first_input_ps']+100
    value = at_value(tmp_path,'l1_c',t)
    inject_value(tmp_path,'tb_capture.dut.l1_c',t,'x' if unknown else format(value^1,'b'))
    inject_value(tmp_path,'tb_capture.dut.l1_c',t+1,format(value,'b'))
    result = compare_activity(tmp_path)
    assert_numpy_report_oracle(result)
    row = next(r for r in result['observations'] if r['signal']=='l1_c')
    if unknown:
        assert row['recorded']['unknown_bit_changes'] == 48
        assert 'X/Z' in row['recorded_interpretation']
    else:
        assert row['recorded_minus_settled_known_changes'] == 2
        assert 'intermediate' in row['recorded_interpretation']


@pytest.mark.parametrize('fault',['numpy_order','nonbinary_numpy','scores','class','unknown_sample',
                                 'missing_hash','hash','rtl','ledger','row_order'])
def test_inconsistent_evidence_rejected_with_failed_report(tmp_path,fault):
    manifest = make_capture(tmp_path)
    if fault in ('numpy_order','nonbinary_numpy'):
        p=tmp_path/'x_test_bits.npy'
        values=np.load(p)
        if fault=='numpy_order':
            values=values[::-1]
        else:
            values=values.astype(np.uint8)
            values[0,0]=2
        np.save(p,values)
        refresh_hash(tmp_path,p.name)
    elif fault in ('scores','class'):
        p=tmp_path/('exp_scores.hex' if fault=='scores' else 'exp_class.hex')
        lines=p.read_text().splitlines()
        lines[0]=format(int(lines[0],16)^1,'x')
        p.write_text('\n'.join(lines)+'\n')
        refresh_hash(tmp_path,p.name)
    elif fault=='unknown_sample':
        inject_value(tmp_path,'tb_capture.dut.l1_c',manifest['events']['first_input_ps']+1,'x')
    elif fault=='missing_hash':
        p=tmp_path/'result.json'
        data=json.loads(p.read_text())
        del data['files_sha256']['x_test_bits.npy']
        p.write_text(json.dumps(data))
    elif fault in ('hash','rtl'):
        p=tmp_path/'dlgn_top.sv'
        p.write_text(p.read_text()+'// unsupported source\n')
        if fault=='rtl':
            refresh_hash(tmp_path,p.name)
    elif fault=='ledger':
        p=tmp_path/'events.csv'
        p.write_text(p.read_text().replace('input,0,291669,4','input,0,291670,4'))
        refresh_hash(tmp_path,p.name)
    else:
        p=tmp_path/'input_indices.json'
        p.write_text(json.dumps(list(reversed(range(16)))))
        refresh_hash(tmp_path,p.name)
    with pytest.raises(ValueError):
        compare_activity(tmp_path)
    failed_result(tmp_path)
