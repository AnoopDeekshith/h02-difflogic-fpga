"""Step 3.8: fresh zero-delay iCE40 UltraPlus standalone-core mapped activity.

Uses the verified step 3.3 archive as the frozen source/workload. This is a
new technology map of the standalone head-only core, not the archived routed
UART board netlist, a delay simulation, or an energy measurement.
"""
import argparse
import csv
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
from dlgn import hard  # noqa: E402
from dlgn.export_verilog import emit_rtl, write_vectors  # noqa: E402
from dlgn.vcd_activity import analyze_vcd  # noqa: E402
from check_waveform_recording import digest  # noqa: E402
from capture_baseline_waveform import validate_events  # noqa: E402
from mapped_activity import port_widths, instrument_json, count_activity, validate_port_bus  # noqa: E402
from report_activity_windows import _snapshots, _known, validate_windows  # noqa: E402

COPY = ('dlgn_top.sv', 'params.json', 'model.json', 'x_test_bits.npy',
        'input_indices.json', 'x.hex', 'exp_scores.hex', 'exp_class.hex',
        'capture_params.svh')
BASELINE_FILES = set(COPY + ('tb_activity_capture.sv', 'commands.json',
                             'build.log', 'sim.log', 'events.csv', 'dlgn.vcd', 'simv'))
SOURCE_FILES = (Path(__file__).resolve(), ROOT/'scripts/mapped_activity.py',
                ROOT/'rtl/tb_mapped_capture.sv', ROOT/'dlgn/hard.py',
                ROOT/'dlgn/gates.py', ROOT/'dlgn/export_verilog.py',
                ROOT/'dlgn/vcd_activity.py', ROOT/'scripts/report_activity_windows.py',
                ROOT/'scripts/capture_baseline_waveform.py',
                ROOT/'scripts/check_waveform_recording.py')


def _run(command, folder, log, timeout=300):
    proc = subprocess.run(command, cwd=folder, capture_output=True, text=True, timeout=timeout)
    (folder/log).write_text(proc.stdout + proc.stderr)
    if proc.returncode:
        raise RuntimeError(f'Command failed ({proc.returncode}); see {folder/log}')


def _tools():
    out = {}
    # Companions must come from the same install as the located primary tool,
    # so synthesis and the simulation cell library use one Yosys version.
    for name, sibling_of in (('yosys', None), ('yosys-config', 'yosys'),
                             ('iverilog', None), ('vvp', 'iverilog')):
        located = (shutil.which(name) if sibling_of is None
                   else Path(out[sibling_of]['path']).parent/name)
        if not located or not Path(located).is_file():
            raise RuntimeError(f'{name} is required' + (
                f' next to {sibling_of}' if sibling_of else ''))
        path = Path(located).resolve()
        version_flag = '-V' if name != 'yosys-config' else '--version'
        proc = subprocess.run([str(path), version_flag], capture_output=True, text=True, check=True)
        out[name] = dict(path=str(path), sha256=digest(path), version=(proc.stdout+proc.stderr).strip())
    return out


def _source_check(baseline):
    manifest_path = baseline/'result.json'
    manifest_hash = digest(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('status') != 'passed' or not isinstance(manifest.get('files_sha256'), dict):
        raise ValueError('Expected passed step 3.3 capture archive')
    archived = manifest['files_sha256']
    if set(archived) != BASELINE_FILES:
        raise ValueError('Baseline archive must hash all 16 expected files')
    for name, expected in archived.items():
        if Path(name).name != name or digest(baseline/name) != expected:
            raise ValueError(f'Baseline artifact changed or unsafe name: {name}')
    params = json.loads((baseline/'params.json').read_text())
    if params != manifest['params'] or params['LAT'] != 3 or params['head_pipeline'] is not True:
        raise ValueError('Expected frozen head-only three-stage core')
    if manifest['clock']['nominal_hz'] != 12_000_000 or manifest['clock']['half_period_ps'] != 41667:
        raise ValueError('Expected fixed nominal 12 MHz schedule')
    n = manifest['n_images']
    if json.loads((baseline/'input_indices.json').read_text()) != list(range(n)):
        raise ValueError('Input order differs from archived order')
    events = validate_events(baseline/'events.csv', n, params)
    if events != manifest['events']:
        raise ValueError('Baseline event ledger differs from manifest')
    # Verify the source trace including all controls, image/order markers,
    # reference scores/classes and settled internal observations before reuse.
    validate_windows(baseline, manifest)
    net = hard.load(baseline/'model.json')
    x = np.load(baseline/'x_test_bits.npy', allow_pickle=False)
    if x.shape != (n, params['IN']) or not np.isin(x, [0,1]).all():
        raise ValueError('Archived input tensor shape differs from core')
    rtl, fresh_params = emit_rtl(net, pipeline=False, head_pipeline=True)
    if rtl != (baseline/'dlgn_top.sv').read_text() or fresh_params != params:
        raise ValueError('Archived RTL/parameters do not regenerate from frozen model')
    return manifest, manifest_hash, net, x


def _validate_mapped_ports(folder, params, n, events, mapped, ledger):
    """Validate actual mapped clock, reset, valid, data, markers and outputs."""
    half = 41667
    period = 2*half
    first = events['first_input_ps']
    last_check = events['last_output_check_ps']
    done = events['capture_done_ps']
    if first != 7*half or events['last_input_ps'] != first+(n-1)*period or (
            last_check != first+(n-1+params['LAT']-1)*period+1):
        raise ValueError('Mapped ledger violates frozen schedule')
    required = {name: ['tb_capture', 'dut'] for name in
                ('clk', 'rst', 'in_valid', 'x', 'out_valid', 'class_out', 'scores',
                 'activity_nodes')}
    required.update({name: ['tb_capture'] for name in
                     ('input_index', 'output_index', 'input_count', 'output_count',
                      'cycle_index', 'capture_done')})
    times = list(range(0, done+1, half)) + [last_check]
    times += [first+i*period for i in range(n)]
    times += [first+i*period+(params['LAT']-1)*period+1 for i in range(n)]
    selected, sampled, rising, falling, changes, final = _snapshots(folder/'mapped.vcd', required, times)
    widths = {'clk':1, 'rst':1, 'in_valid':1, 'x':params['IN'], 'out_valid':1,
              'class_out':params['CW'], 'scores':params['K']*params['SW'],
              'capture_done':1}
    for name in ('input_index', 'output_index', 'input_count', 'output_count', 'cycle_index'):
        widths[name] = 32
    for name, width in widths.items():
        if selected[name]['width'] != width:
            raise ValueError(f'Incorrect mapped port/marker width {name}')
    if selected['activity_nodes']['width'] != len(ledger['entries']):
        raise ValueError('Canonical mapped bus width differs from ledger')
    bit_to_index = {entry['bit_id']:i for i,entry in enumerate(ledger['entries'])}
    top_ports = mapped['modules']['dlgn_top']['ports']
    for at_time, snapshot in sampled.items():
        bus = snapshot['activity_nodes']
        if bus is None:
            raise ValueError('Canonical mapped bus is absent at port sample')
        for port_name, port in top_ports.items():
            state = snapshot[port_name]
            if state is None:
                raise ValueError(f'Mapped port {port_name} absent at sample')
            for offset, bit in enumerate(port['bits']):
                if type(bit) is not int:
                    continue
                position = bit_to_index[bit]
                mask = 1 << position
                port_mask = 1 << offset
                bus_bit = tuple(bool(part & mask) for part in bus)
                port_bit = tuple(bool(part & port_mask) for part in state)
                if bus_bit != port_bit:
                    raise ValueError(f'Canonical bit {bit} disagrees with {port_name}[{offset}] at {at_time}')
    if rising != list(range(half, done+1, period)) or (
            falling != list(range(period, done+1, period)) or final != done+1):
        raise ValueError('Mapped clock cadence or trace tail differs')
    if changes['rst'] != [(0,(1,0,0)), (6*half,(0,0,0))]:
        raise ValueError('Mapped reset sequence differs')
    if changes['in_valid'] != [(0,(0,0,0)), (first-half,(1,0,0)),
                               (events['last_input_ps']+half,(0,0,0))]:
        raise ValueError('Mapped input valid sequence differs')
    if [(t,v) for t,v in changes['out_valid'] if t >= 6*half] != [
            (events['first_output_check_ps']-1,(1,0,0)),
            (last_check-1+period,(0,0,0))]:
        raise ValueError('Mapped output valid sequence differs')
    inputs = [int(v,16) for v in (folder/'x.hex').read_text().split()]
    scores = [int(v,16) for v in (folder/'exp_scores.hex').read_text().split()]
    classes = [int(v,16) for v in (folder/'exp_class.hex').read_text().split()]
    if len(inputs) != n or len(scores) != n or len(classes) != n:
        raise ValueError('Mapped reference count differs')
    expected_x = [(0,(0,0,0))]
    previous = 0
    for i, x in enumerate(inputs):
        if x != previous:
            expected_x.append((first-half+i*period,(x,0,0)))
        previous = x
    if changes['x'] != expected_x:
        raise ValueError('Mapped input values or hold schedule differ')
    for i in range(n):
        at = sampled[first+i*period]
        if any(_known(at,k) != v for k,v in
               (('clk',1),('rst',0),('in_valid',1),('x',inputs[i]),
                ('input_index',i),('input_count',i+1))):
            raise ValueError(f'Mapped input/marker mismatch at {i}')
        out = sampled[first+i*period+(params['LAT']-1)*period+1]
        if any(_known(out,k) != v for k,v in
               (('clk',1),('rst',0),('out_valid',1),('scores',scores[i]),
                ('class_out',classes[i]),('output_index',i),('output_count',i+1))):
            raise ValueError(f'Mapped score/class/marker mismatch at {i}')
    ending = sampled[done]
    if any(_known(ending,k) != v for k,v in
           (('in_valid',0),('out_valid',0),('x',inputs[-1]),
            ('input_count',n),('output_count',n),('capture_done',1))):
        raise ValueError('Mapped final drain differs')
    return dict(n_images=n, score_class_checks=n, input_checks=n,
                clock_edges=len(rising), output_latency_cycles=params['LAT']-1,
                final_timestamp_ps=final, canonical_port_samples=len(sampled),
                markers_and_full_port_schedule_verified=True)


def capture(baseline_capture_dir):
    baseline = Path(baseline_capture_dir).resolve()
    folder = Path(tempfile.mkdtemp(prefix='mapped-activity.', dir=baseline.parent))
    report = folder/'result.json'
    result = dict(status='running', directory=str(folder), scope=__doc__.strip())
    report.write_text(json.dumps(result, indent=2)+'\n')
    try:
        source, source_hash, net, x = _source_check(baseline)
        for name in COPY:
            shutil.copyfile(baseline/name, folder/name)
        shutil.copyfile(baseline/'result.json', folder/'baseline-manifest.json')
        (folder/'sources').mkdir()
        source_hashes = {str(p): digest(p) for p in SOURCE_FILES}
        for source_file in SOURCE_FILES:
            shutil.copyfile(source_file, folder/'sources'/source_file.name)
            if digest(folder/'sources'/source_file.name) != source_hashes[str(source_file)]:
                raise ValueError(f'Source changed while copying {source_file.name}')
        write_vectors(net, x, folder, source['params'])
        for name in ('x.hex', 'exp_scores.hex', 'exp_class.hex'):
            if digest(folder/name) != source['files_sha256'][name]:
                raise ValueError(f'Fresh NumPy reference differs from archived {name}')
        shutil.copyfile(ROOT/'rtl/tb_mapped_capture.sv', folder/'tb_mapped_capture.sv')
        tools = _tools()
        datdir = subprocess.check_output([tools['yosys-config']['path'], '--datdir'], text=True).strip()
        library = Path(datdir)/'ice40/cells_sim.v'
        shutil.copyfile(library, folder/'cells_sim.v')
        commands = [
            [tools['yosys']['path'], '-Q', '-l', 'synth.log', '-p',
             'read_verilog -sv dlgn_top.sv; synth_ice40 -device u -top dlgn_top -json mapped.json; stat'],
            [tools['yosys']['path'], '-Q', '-l', 'write.log', '-p',
             'read_json instrumented.json; write_verilog -noattr mapped_core.v'],
            [tools['iverilog']['path'], '-g2012', '-s', 'tb_capture', '-o', 'simv',
             'tb_mapped_capture.sv', 'mapped_core.v', 'cells_sim.v'],
            [tools['vvp']['path'], 'simv']]
        (folder/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        _run(commands[0], folder, 'synth.stdout.log', timeout=300)
        mapped = json.loads((folder/'mapped.json').read_text())
        instrumented, ledger = instrument_json(mapped, port_widths(source['params']))
        (folder/'instrumented.json').write_text(json.dumps(instrumented, sort_keys=True)+'\n')
        (folder/'net-ledger.json').write_text(json.dumps(ledger, indent=2)+'\n')
        _run(commands[1], folder, 'write.stdout.log')
        _run(commands[2], folder, 'build.log')
        _run(commands[3], folder, 'sim.log', timeout=300)
        n = source['n_images']
        if f'PASS: {n}/{n} mapped vectors bit-exact (scores + class)' not in (folder/'sim.log').read_text():
            raise ValueError('Missing complete mapped score/class pass')
        events = validate_events(folder/'events.csv', n, source['params'])
        if events != source['events']:
            raise ValueError('Mapped event ledger differs from baseline')
        ports = _validate_mapped_ports(folder, source['params'], n, events, mapped, ledger)
        ports['continuous_bus_to_port'] = validate_port_bus(folder/'mapped.vcd', mapped, ledger)
        waveform = analyze_vcd(folder/'mapped.vcd')
        if waveform['timescale']['unit'] != 'ps' or waveform['timescale']['magnitude'] != 1:
            raise ValueError('Mapped trace does not use 1 ps ticks')
        burst_start = events['first_input_ps']-41667-1
        burst_end = events['last_output_check_ps']
        whole = count_activity(folder/'mapped.vcd', ledger)
        burst = count_activity(folder/'mapped.vcd', ledger, burst_start, burst_end)
        if digest(baseline/'result.json') != source_hash or any(
                digest(baseline/name) != expected for name,expected in source['files_sha256'].items()):
            raise ValueError('Baseline source changed during mapped capture')
        if any(digest(folder/name) != source['files_sha256'][name] for name in COPY):
            raise ValueError('Frozen copied source changed during mapped capture')
        if {str(p): digest(p) for p in SOURCE_FILES} != source_hashes:
            raise ValueError('Analysis source changed during mapped capture')
        files = [str(p.relative_to(folder)) for p in folder.rglob('*')
                 if p.is_file() and p != report]
        result.update(status='passed', baseline_capture=str(baseline),
                      baseline_manifest_sha256=source_hash,
                      baseline_artifacts_sha256=source['files_sha256'],
                      original_hardware_binding=source.get('hardware_binding'),
                      source_sha256=source_hashes,
                      tool_evidence=tools, library_source=str(library),
                      library_sha256=digest(library), commands=commands,
                      mapping=dict(device='iCE40 UltraPlus (-device u)',
                                   design='fresh standalone head-only core',
                                   historic_board_mapping='separate UART board synthesis; no mapped-net identity claim',
                                   primitive_counts=ledger['primitive_counts'],
                                   net_bit_count=len(ledger['entries']),
                                   category_bit_counts=ledger['category_bits']),
                      simulation=dict(mode='Icarus functional iCE40 primitives; no specify timing flags',
                                      clock_nominal_hz=12_000_000, half_period_ps=41667,
                                      initialization='cells_sim.v SB_DFF_INIT initializes Q to zero; not electrical startup',
                                      ports=ports, event_ledger=events),
                      activity=dict(whole_trace=whole, complete_burst=burst,
                                    complete_burst_note='(first data drive - 1 ps, final output check]; includes fill and output drain; diagnostic total, not energy denominator'),
                      limits=['Zero-delay primitive simulation does not establish physical glitches or energy',
                              'Fresh standalone core mapping is not archived flattened routed UART board netlist',
                              'Historical exploratory baseline is not matched retrained control',
                              'No routed timing, physical power, energy or novelty claim'],
                      files_sha256={name:digest(folder/name) for name in sorted(files)})
    except Exception as exc:
        result.update(status='failed', error=str(exc))
        raise
    finally:
        report.write_text(json.dumps(result, indent=2)+'\n')
        print(f'Mapped activity evidence: {report}', flush=True)
    return result


def analyze(mapped_capture_dir):
    capture_dir = Path(mapped_capture_dir).resolve()
    folder = Path(tempfile.mkdtemp(prefix='mapped-analysis.', dir=capture_dir))
    report = folder/'result.json'
    result = dict(status='running', directory=str(folder))
    report.write_text(json.dumps(result, indent=2)+'\n')
    try:
        original = capture_dir/'result.json'
        original_hash = digest(original)
        manifest = json.loads(original.read_text())
        if manifest.get('status') != 'passed':
            raise ValueError('Expected passed mapped capture')
        required = set(COPY) | {'baseline-manifest.json', 'tb_mapped_capture.sv',
             'cells_sim.v', 'commands.json', 'mapped.json', 'instrumented.json',
             'net-ledger.json', 'mapped_core.v', 'simv', 'mapped.vcd', 'events.csv',
             'synth.log', 'write.log', 'synth.stdout.log', 'write.stdout.log',
             'build.log', 'sim.log'}
        if not required <= set(manifest.get('files_sha256', {})):
            raise ValueError('Mapped archive lacks required hashed artifacts')
        for name, expected in manifest['files_sha256'].items():
            if Path(name).is_absolute() or '..' in Path(name).parts or (
                    digest(capture_dir/name) != expected):
                raise ValueError(f'Mapped artifact changed or unsafe name: {name}')
        baseline = Path(manifest['baseline_capture']).resolve()
        source, source_hash, net, x = _source_check(baseline)
        if source_hash != manifest['baseline_manifest_sha256'] or (
                json.loads((capture_dir/'baseline-manifest.json').read_text()) != source):
            raise ValueError('Baseline manifest changed since mapped capture')
        for name in COPY:
            if digest(capture_dir/name) != source['files_sha256'][name]:
                raise ValueError(f'Mapped copy differs from baseline {name}')
        (folder/'reference').mkdir()
        write_vectors(net, x, folder/'reference', source['params'])
        for name in ('x.hex', 'exp_scores.hex', 'exp_class.hex'):
            if digest(folder/'reference'/name) != digest(capture_dir/name):
                raise ValueError(f'Mapped reference differs from fresh NumPy {name}')
        mapped = json.loads((capture_dir/'mapped.json').read_text())
        instrumented, derived_ledger = instrument_json(mapped, port_widths(source['params']))
        if instrumented != json.loads((capture_dir/'instrumented.json').read_text()):
            raise ValueError('Instrumented mapping differs from original JSON')
        ledger = json.loads((capture_dir/'net-ledger.json').read_text())
        if ledger != derived_ledger:
            raise ValueError('Mapped ledger differs from original JSON')
        events = manifest['simulation']['event_ledger']
        if validate_events(capture_dir/'events.csv', source['n_images'], source['params']) != events or (
                events != source['events']):
            raise ValueError('Mapped event ledger differs from baseline')
        _validate_mapped_ports(capture_dir, source['params'], source['n_images'],
                               events, mapped, ledger)
        validate_port_bus(capture_dir/'mapped.vcd', mapped, ledger)
        start = events['first_input_ps']-41667-1
        end = events['last_output_check_ps']
        whole = count_activity(capture_dir/'mapped.vcd', ledger)
        burst = count_activity(capture_dir/'mapped.vcd', ledger, start, end)
        if whole != manifest['activity']['whole_trace'] or burst != manifest['activity']['complete_burst']:
            raise ValueError('Reanalysis differs from recorded capture')
        if digest(original) != original_hash:
            raise ValueError('Mapped capture manifest changed during analysis')
        shutil.copyfile(original, folder/'capture-manifest.json')
        result.update(status='passed', capture_directory=str(capture_dir),
                      capture_manifest_sha256=original_hash,
                      source_sha256={str(p):digest(p) for p in
                                     (Path(__file__).resolve(), ROOT/'scripts/mapped_activity.py')},
                      activity=dict(whole_trace=whole, complete_burst=burst),
                      files_sha256={'capture-manifest.json':digest(folder/'capture-manifest.json')})
    except Exception as exc:
        result.update(status='failed', error=str(exc))
        raise
    finally:
        report.write_text(json.dumps(result, indent=2)+'\n')
        print(f'Mapped reanalysis evidence: {report}', flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for action in ('capture', 'analyze'):
        sub.add_parser(action).add_argument('directory', type=Path)
    args = parser.parse_args()
    (capture if args.action == 'capture' else analyze)(args.directory)
