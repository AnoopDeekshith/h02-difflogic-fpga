"""Capture all historical inputs using the feasible head-only core at nominal 12 MHz.

This is standalone streaming zero-delay RTL. No UART, delay/glitch, activity
total, physical power or energy result is produced.
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
sys.path.insert(0, str(ROOT / 'scripts'))
from dlgn import hard  # noqa: E402
from dlgn.export_verilog import emit_rtl, write_vectors  # noqa: E402
from check_waveform_recording import digest, inspect_vcd  # noqa: E402
from report_performance import implementation_evidence  # noqa: E402

HALF_PERIOD_PS = 41667


def write_parameters(folder, params, n, half_period_ps=HALF_PERIOD_PS):
    definitions = {k: params[k] for k in ('IN', 'K', 'SW', 'CW', 'LAT')}
    definitions.update(N=n, HALF_PERIOD_PS=half_period_ps)
    (Path(folder) / 'capture_params.svh').write_text(
        '\n'.join(f'parameter {k}={v};' for k, v in definitions.items()) + '\n')


def validate_events(path, n, params, half_period_ps=HALF_PERIOD_PS):
    """Verify the bench's capture/check ledger, not waveform activity totals."""
    with Path(path).open() as f:
        rows = list(csv.DictReader(f))
    if len(rows) != 2*n + 1 or any(row['kind'] not in ('input', 'output', 'done') for row in rows):
        raise ValueError('Unexpected capture event count/kind')
    groups = {kind: [row for row in rows if row['kind'] == kind]
              for kind in ('input', 'output', 'done')}
    period = 2 * half_period_ps
    for kind in ('input', 'output'):
        if [int(row['index']) for row in groups[kind]] != list(range(n)):
            raise ValueError(f'{kind} indices are missing, duplicated or reordered')
        times = [int(row['time_ps']) for row in groups[kind]]
        cycles = [int(row['cycle']) for row in groups[kind]]
        if any(b-a != period for a, b in zip(times, times[1:])) or any(
                b-a != 1 for a, b in zip(cycles, cycles[1:])):
            raise ValueError(f'{kind} cadence differs from fixed streaming workload')
    for inp, out in zip(groups['input'], groups['output']):
        if int(out['time_ps']) - int(inp['time_ps']) != (params['LAT']-1)*period + 1 or (
                int(out['cycle']) - int(inp['cycle']) != params['LAT']-1):
            raise ValueError('Output ledger violates post-update latency')
    done = groups['done']
    if len(done) != 1 or rows[-1] != done[0] or int(done[0]['index']) != -1:
        raise ValueError('Missing final capture marker')
    if int(done[0]['time_ps']) <= int(groups['output'][-1]['time_ps']):
        raise ValueError('Capture finished before outputs drained')
    return dict(input_count=n, output_count=n,
                first_input_ps=int(groups['input'][0]['time_ps']),
                last_input_ps=int(groups['input'][-1]['time_ps']),
                first_output_check_ps=int(groups['output'][0]['time_ps']),
                last_output_check_ps=int(groups['output'][-1]['time_ps']),
                capture_done_ps=int(done[0]['time_ps']),
                output_check_offset_ps=1,
                port_latency_cycles=params['LAT']-1,
                scope='Ledger boundaries for future analysis; not a validated switching window')


def capture(run, board_export, implementation):
    run, board_export, implementation = (Path(p).resolve() for p in (run, board_export, implementation))
    folder = Path(tempfile.mkdtemp(prefix='baseline-waveform.', dir=run))
    report = folder / 'result.json'
    result = dict(status='running', directory=str(folder), scope=__doc__.strip())
    report.write_text(json.dumps(result, indent=2) + '\n')
    try:
        if board_export.parent != run:
            raise ValueError('Board export must belong to the supplied model run')
        qualified = implementation_evidence(board_export, implementation)
        if not qualified['timing_qualified']:
            raise ValueError('Capture requires the feasible timing-qualified head candidate')
        net = hard.load(run / 'model.json')
        rtl, params = emit_rtl(net, pipeline=False, head_pipeline=True)
        exported = json.loads((board_export / 'params.json').read_text())
        if rtl != (board_export / 'dlgn_top.sv').read_text() or any(
                exported.get(k) != v for k, v in params.items()):
            raise ValueError('Model does not regenerate the bound head-only core')
        if exported.get('clock_hz') != 12_000_000:
            raise ValueError('Board clock differs from the frozen nominal 12 MHz target')
        x = np.load(run / 'x_test_bits.npy')
        if x.ndim != 2 or x.shape[1] != params['IN'] or len(x) < 2:
            raise ValueError('Expected all ordered saved input vectors with matching width')
        if not np.isin(x, (0, 1)).all():
            raise ValueError('Saved input vectors must contain only 0/1 bits')
        n = len(x)
        (folder / 'dlgn_top.sv').write_text(rtl)
        (folder / 'params.json').write_text(json.dumps(params, indent=2) + '\n')
        for name in ('model.json', 'x_test_bits.npy'):
            shutil.copyfile(run / name, folder / name)
        (folder / 'input_indices.json').write_text(json.dumps(list(range(n))) + '\n')
        write_vectors(net, x, folder, params)
        write_parameters(folder, params, n)
        shutil.copyfile(ROOT / 'rtl/tb_activity_capture.sv', folder / 'tb_activity_capture.sv')
        sources = [run / 'model.json', run / 'x_test_bits.npy', board_export / 'dlgn_top.sv',
                   board_export / 'params.json', ROOT / 'rtl/tb_activity_capture.sv',
                   ROOT / 'dlgn/export_verilog.py', ROOT / 'dlgn/hard.py', ROOT / 'dlgn/gates.py',
                   ROOT / 'scripts/check_waveform_recording.py', Path(__file__).resolve(),
                   ROOT / 'scripts/report_performance.py', ROOT / 'scripts/report_timing.py',
                   ROOT / 'scripts/build_artifacts.py']
        result.update(n_images=n, params=params,
                      source_sha256={str(p): digest(p) for p in sources},
                      hardware_binding=dict(export=str(board_export), implementation=str(implementation),
                                            evidence=qualified),
                      clock=dict(nominal_hz=12_000_000, half_period_ps=HALF_PERIOD_PS,
                                 simulated_period_ps=2*HALF_PERIOD_PS,
                                 simulated_hz=1e12/(2*HALF_PERIOD_PS), precision_ps=1,
                                 note='1 ps rounding; archived implementation target remains unchanged'),
                      workload=dict(interface='standalone core, not UART',
                                    input_source='all saved x_test_bits.npy rows in unchanged order',
                                    initiation_interval_cycles=1, reset_cycles=3,
                                    drive_phase='falling edge', output_check='rising edge plus 1 ps',
                                    drain='hold final image; three falling edges after final output check',
                                    baseline='historical exploratory model; no retraining or selection'))
        tools = {}
        for tool in ('iverilog', 'vvp'):
            executable = shutil.which(tool)
            if not executable:
                raise RuntimeError(f'{tool} is required')
            executable = str(Path(executable).resolve())
            version = subprocess.run([executable, '-V'], capture_output=True, text=True, check=True)
            tools[tool] = dict(path=executable, sha256=digest(executable), version=version.stdout+version.stderr)
        result['simulators'] = tools
        commands = [[tools['iverilog']['path'], '-g2012', '-s', 'tb_capture', '-o', 'simv',
                     'tb_activity_capture.sv', 'dlgn_top.sv'], [tools['vvp']['path'], 'simv']]
        (folder / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
        for name, command in zip(('build.log', 'sim.log'), commands):
            proc = subprocess.run(command, cwd=folder, capture_output=True, text=True, timeout=120)
            (folder / name).write_text(proc.stdout+proc.stderr)
            if proc.returncode:
                raise RuntimeError(f'Capture failed; see {folder/name}')
        if f'PASS: {n}/{n} baseline vectors bit-exact (scores + class)' not in (folder/'sim.log').read_text():
            raise ValueError('Missing complete score/class simulation pass')
        result['events'] = validate_events(folder/'events.csv', n, params)
        result['waveform'] = inspect_vcd(folder/'dlgn.vcd', params)
        if result['waveform']['final_timestamp'] < result['events']['capture_done_ps']:
            raise ValueError('Waveform ends before completed capture')
        files = ('dlgn_top.sv', 'params.json', 'model.json', 'x_test_bits.npy',
                 'input_indices.json', 'x.hex', 'exp_scores.hex', 'exp_class.hex',
                 'capture_params.svh', 'tb_activity_capture.sv', 'commands.json',
                 'build.log', 'sim.log', 'events.csv', 'dlgn.vcd', 'simv')
        result['files_sha256'] = {name: digest(folder/name) for name in files}
        result['status'] = 'passed'
    except Exception as exc:
        result.update(status='failed', error=str(exc))
        raise
    finally:
        report.write_text(json.dumps(result, indent=2) + '\n')
        print(f'Baseline capture evidence: {report}', flush=True)
    return result


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('run', type=Path)
    ap.add_argument('--export', type=Path, required=True)
    ap.add_argument('--implementation', type=Path, required=True)
    args = ap.parse_args()
    capture(args.run, args.export, args.implementation)
