"""Independent step 3.5 checks of stage-aligned useful-work windows."""
import hashlib
import json
from bisect import bisect_right
from pathlib import Path
import shutil
import subprocess
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from dlgn.export_verilog import emit_rtl, write_vectors  # noqa: E402
from capture_baseline_waveform import validate_events, write_parameters  # noqa: E402


def make_capture(folder, pipeline=False, head=True, repeated=False):
    """Create self-contained simulation evidence, without claiming routing."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if not shutil.which('iverilog') or not shutil.which('vvp'):
        pytest.skip('Icarus required for activity-window verification')
    rng = np.random.default_rng(73)
    layers = []
    previous = 4
    for _ in range(3):
        layers.append(dict(ia=rng.integers(previous, size=24).tolist(),
                           ib=rng.integers(previous, size=24).tolist(),
                           gates=np.tile([6, 8, 14, 12, 10, 0], 4).tolist()))
        previous = 24
    net = dict(in_dim=4, n_classes=4, layers=layers)
    x = ((np.arange(16)[:, None] >> np.arange(4)) & 1).astype(bool)
    if repeated:
        x[:] = 0
    rtl, params = emit_rtl(net, pipeline=pipeline, head_pipeline=head)
    (folder/'dlgn_top.sv').write_text(rtl)
    (folder/'model.json').write_text(json.dumps(net))
    (folder/'params.json').write_text(json.dumps(params))
    np.save(folder/'x_test_bits.npy', x)
    (folder/'input_indices.json').write_text(json.dumps(list(range(len(x)))))
    write_vectors(net, x, folder, params)
    write_parameters(folder, params, len(x))
    shutil.copyfile(ROOT/'rtl/tb_activity_capture.sv', folder/'tb_activity_capture.sv')
    commands = [['iverilog', '-g2012', '-s', 'tb_capture', '-o', 'simv',
                 'tb_activity_capture.sv', 'dlgn_top.sv'], ['vvp', 'simv']]
    (folder/'commands.json').write_text(json.dumps(commands))
    for name, command in zip(('build.log', 'sim.log'), commands):
        completed = subprocess.run(command, cwd=folder, capture_output=True, text=True, timeout=30)
        (folder/name).write_text(completed.stdout+completed.stderr)
        assert completed.returncode == 0, completed.stdout+completed.stderr
    manifest = dict(status='passed', n_images=len(x), params=params,
                    events=validate_events(folder/'events.csv', len(x), params),
                    clock=dict(nominal_hz=12_000_000, half_period_ps=41667,
                               simulated_period_ps=83334, precision_ps=1),
                    workload=dict(interface='standalone core, not UART',
                                  initiation_interval_cycles=1, reset_cycles=3,
                                  drive_phase='falling edge',
                                  output_check='rising edge plus 1 ps',
                                  drain='hold final image; three falling edges after final output check'))
    names = ('dlgn_top.sv', 'params.json', 'model.json', 'x_test_bits.npy',
             'input_indices.json', 'x.hex', 'exp_scores.hex', 'exp_class.hex',
             'capture_params.svh', 'tb_activity_capture.sv', 'commands.json',
             'build.log', 'sim.log', 'events.csv', 'dlgn.vcd', 'simv')
    manifest['files_sha256'] = {name: hashlib.sha256((folder/name).read_bytes()).hexdigest()
                               for name in names}
    (folder/'result.json').write_text(json.dumps(manifest))
    return manifest


def refresh_hash(folder, name):
    path = Path(folder)/'result.json'
    manifest = json.loads(path.read_text())
    manifest['files_sha256'][name] = hashlib.sha256((Path(folder)/name).read_bytes()).hexdigest()
    path.write_text(json.dumps(manifest))


def trace_values(path):
    """Independent decoder for Icarus's complete per-line VCD output."""
    stack, declarations, identifiers, values, snapshots = [], {}, {}, {}, {}
    body, timestamp = False, 0
    for line in Path(path).read_text().splitlines():
        words = line.split()
        if not words:
            continue
        if not body:
            if words[0] == '$scope':
                stack.append(words[2])
            elif words[0] == '$upscope':
                stack.pop()
            elif words[0] == '$var':
                name = '.'.join(stack+[words[4]])
                declarations[name] = (words[3], int(words[2]))
                identifiers.setdefault(words[3], []).append(name)
            elif words[0] == '$enddefinitions':
                body = True
            continue
        if words[0].startswith('#'):
            snapshots[timestamp] = values.copy()
            timestamp = int(words[0][1:])
        elif words[0][0] in 'bB' and len(words) == 2:
            bits, identifier = words[0][1:], words[1]
            for name in identifiers.get(identifier, []):
                values[name] = None if set(bits.lower()) & {'x','z'} else int(bits, 2)
        elif words[0][0] in '01xXzZ':
            bit, identifier = words[0][0], words[0][1:]
            for name in identifiers.get(identifier, []):
                values[name] = int(bit) if bit in '01' else None
    snapshots[timestamp] = values.copy()
    return declarations, snapshots


def api():
    from report_activity_windows import derive_windows, report_windows
    return derive_windows, report_windows


def by_signal(windows):
    return {row['signal'].split('.')[-1].split('[')[0]: row for row in windows}


def at(snapshots, timestamp):
    times = sorted(snapshots)
    return snapshots[times[bisect_right(times, timestamp)-1]]


@pytest.mark.parametrize('pipeline,head', [(False,False),(False,True),(True,False),(True,True)])
def test_derived_windows_align_all_stages_to_identical_frame_pairs(pipeline, head):
    derive_windows, _ = api()
    depth, n, half, first = 4, 450, 41667, 291669
    period = 2*half
    params = dict(D=depth, LAT=(depth+2 if pipeline else 2)+int(head), head_pipeline=head)
    windows = by_signal(derive_windows(params, first, n, half))
    offsets = dict(x=-half, l0=0,
                   sc_flat=((depth if pipeline else 0)+int(head))*period,
                   best=((depth if pipeline else 0)+int(head))*period,
                   scores=(params['LAT']-1)*period,
                   class_out=(params['LAT']-1)*period)
    for d in range(1,depth+1):
        offsets[f'l{d}'] = d*period if pipeline else 0
        offsets[f'l{d}_c'] = (d-1)*period if pipeline else 0
    assert windows.keys() == offsets.keys()
    for name, offset in offsets.items():
        row = windows[name]
        assert row['offset_from_input_ps'] == offset
        assert row['first_sample_ps'] == first+offset+1
        assert row['last_sample_ps'] == first+offset+1+(n-1)*period
        assert row['start_exclusive_tick'] == row['first_sample_ps']
        assert row['end_inclusive_tick'] == row['last_sample_ps']
        assert row['sample_count'] == n and row['adjacent_pairs'] == n-1
        assert row['duration_ps'] == (n-1)*period


@pytest.mark.parametrize('pipeline,head', [(False,False),(False,True),(True,False),(True,True)])
def test_window_report_matches_independent_vcd_endpoints(tmp_path, pipeline, head):
    _, report_windows = api()
    manifest = make_capture(tmp_path, pipeline=pipeline, head=head)
    result = report_windows(tmp_path)
    assert result['status'] == 'passed'
    windows = by_signal(result['windows'])
    _, snapshots = trace_values(tmp_path/'dlgn.vcd')
    period = 83334
    for name, row in windows.items():
        for index in range(16):
            timestamp = row['first_sample_ps']+index*period
            state = at(snapshots, timestamp)
            assert state['tb_capture.dut.rst'] == 0
            assert state['tb_capture.dut.'+name] is not None
        assert row['sample_count'] == 16 and row['adjacent_pairs'] == 15
        assert row['last_sample_ps']-row['first_sample_ps'] == 15*period
    assert windows['scores']['first_sample_ps'] == manifest['events']['first_output_check_ps']
    assert windows['scores']['last_sample_ps'] == manifest['events']['last_output_check_ps']
    assert windows['l0']['first_sample_ps'] == manifest['events']['first_input_ps']+1
    assert windows['l0']['last_sample_ps'] == manifest['events']['last_input_ps']+1


def test_repeated_inputs_still_have_fifteen_adjacent_pairs(tmp_path):
    _, report_windows = api()
    make_capture(tmp_path,repeated=True)
    result = report_windows(tmp_path)
    assert all(row['sample_count'] == 16 and row['adjacent_pairs'] == 15
               for row in result['windows'])


def inject_value(folder, signal, timestamp, bits):
    path = Path(folder)/'dlgn.vcd'
    declarations, _ = trace_values(path)
    identifier, width = declarations[signal]
    record = f'b{bits} {identifier}' if width > 1 else bits+identifier
    lines = path.read_text().splitlines()
    existing = [i for i,line in enumerate(lines) if line == f'#{timestamp}']
    if existing:
        following = next((i for i in range(existing[0]+1,len(lines)) if lines[i].startswith('#')),len(lines))
        lines.insert(following,record)
    else:
        following = next((i for i,line in enumerate(lines) if line.startswith('#') and int(line[1:]) > timestamp),len(lines))
        lines[following:following] = [f'#{timestamp}',record]
    path.write_text('\n'.join(lines)+'\n')
    refresh_hash(folder,'dlgn.vcd')


@pytest.mark.parametrize('fault', ['ledger_off_by_one','input_bubble','reset_during_frames',
                                 'unknown_layer_sample','input_index','expected_scores',
                                 'trace_hash','missing_last_output','x_between_samples',
                                 'x_during_drain','reset_between_samples','valid_between_samples',
                                 'timescale_mismatch'])
def test_window_report_rejects_unsafe_or_inconsistent_window_evidence(tmp_path,fault):
    _, report_windows = api()
    manifest = make_capture(tmp_path)
    first = manifest['events']['first_input_ps']
    if fault == 'ledger_off_by_one':
        path = tmp_path/'events.csv'
        text = path.read_text().replace(f'input,0,{first},4',f'input,0,{first+1},4')
        path.write_text(text)
        refresh_hash(tmp_path,'events.csv')
    elif fault == 'input_bubble':
        inject_value(tmp_path,'tb_capture.dut.in_valid',first+5*83334,'0')
    elif fault == 'reset_during_frames':
        inject_value(tmp_path,'tb_capture.dut.rst',first+5*83334,'1')
    elif fault == 'unknown_layer_sample':
        inject_value(tmp_path,'tb_capture.dut.l2',first,'x')
    elif fault == 'input_index':
        inject_value(tmp_path,'tb_capture.input_index',first,'11')
    elif fault == 'expected_scores':
        path = tmp_path/'exp_scores.hex'
        lines = path.read_text().splitlines()
        lines[0] = format(int(lines[0],16)^1,'x')
        path.write_text('\n'.join(lines)+'\n')
        refresh_hash(tmp_path,'exp_scores.hex')
    elif fault == 'trace_hash':
        with (tmp_path/'dlgn.vcd').open('a') as dest:
            dest.write('$comment modified without updating manifest $end\n')
    elif fault == 'missing_last_output':
        path = tmp_path/'dlgn.vcd'
        lines = path.read_text().splitlines()
        cutoff = next(i for i,line in enumerate(lines) if line.startswith('#') and int(line[1:]) >= manifest['events']['last_output_check_ps'])
        path.write_text('\n'.join(lines[:cutoff])+'\n')
        refresh_hash(tmp_path,'dlgn.vcd')
    elif fault == 'x_between_samples':
        inject_value(tmp_path,'tb_capture.dut.x',first+100,'1')
        inject_value(tmp_path,'tb_capture.dut.x',first+101,'0')
    elif fault == 'x_during_drain':
        final = int((tmp_path/'x.hex').read_text().split()[-1],16)
        tail = manifest['events']['last_output_check_ps']+100
        inject_value(tmp_path,'tb_capture.dut.x',tail,format(final^1,'b'))
        inject_value(tmp_path,'tb_capture.dut.x',tail+1,format(final,'b'))
    elif fault == 'reset_between_samples':
        inject_value(tmp_path,'tb_capture.dut.rst',first+100,'1')
        inject_value(tmp_path,'tb_capture.dut.rst',first+101,'0')
    elif fault == 'valid_between_samples':
        inject_value(tmp_path,'tb_capture.dut.in_valid',first+100,'0')
        inject_value(tmp_path,'tb_capture.dut.in_valid',first+101,'1')
    elif fault == 'timescale_mismatch':
        path = tmp_path/'dlgn.vcd'
        path.write_text(path.read_text().replace('1ps','1ns',1))
        refresh_hash(tmp_path,'dlgn.vcd')
    with pytest.raises(ValueError):
        report_windows(tmp_path)
    failures = [json.loads(path.read_text()) for path in tmp_path.glob('*/result.json')]
    assert len(failures) == 1 and failures[0]['status'] == 'failed'
