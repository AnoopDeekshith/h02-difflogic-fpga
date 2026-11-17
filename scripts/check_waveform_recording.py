"""Step 3.2: fresh recording-on/off smoke checks, not an activity measurement.

Uses Icarus explicitly. The existing core bench has a nominal 100 MHz clock;
this short mechanism check is not a timing-qualified workload or power trace.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dlgn import hard  # noqa: E402
from dlgn.export_verilog import export  # noqa: E402


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inspect_vcd(path, params):
    """Check required DUT declarations and observable values, not toggle totals.

    Aliases may share VCD identifiers. No event/energy inference is made from
    these observations; measurement windows and settled-output alignment are
    intentionally left for steps 3.4–3.7.
    """
    required = dict(clk=1, rst=1, in_valid=1, out_valid=1,
                    x=params['IN'], scores=params['K'] * params['SW'],
                    class_out=params['CW'], l0=params['IN'])
    required.update({f'l{d}': params['W'] for d in range(1, params['D'] + 1)})
    required.update({f'l{d}_c': params['W'] for d in range(1, params['D'] + 1)})
    scopes, declarations, observations = [], {}, {}
    header_done = False
    timescale_lines = []
    in_timescale = False
    timestamp = 0
    positive_time = False
    with Path(path).open() as f:
        for raw in f:
            line = raw.strip()
            if not header_done:
                if line.startswith('$timescale'):
                    in_timescale = True
                if in_timescale:
                    timescale_lines.append(line)
                    if '$end' in line:
                        in_timescale = False
                parts = line.split()
                if line.startswith('$scope'):
                    scopes.append(parts[2])
                elif line.startswith('$upscope'):
                    scopes.pop()
                elif line.startswith('$var') and scopes[-1:] == ['dut']:
                    _, _, width, code, name, *_ = parts
                    declarations[name] = (int(width), code)
                elif line.startswith('$enddefinitions'):
                    header_done = True
                    missing = set(required) - set(declarations)
                    if missing:
                        raise ValueError(f'Missing DUT signals: {sorted(missing)}')
                    for name, width in required.items():
                        if declarations[name][0] != width:
                            raise ValueError(f'Wrong VCD width for {name}')
                    observations = {declarations[name][1]: set() for name in required}
                continue
            if line.startswith('#'):
                now = int(line[1:])
                if now < timestamp:
                    raise ValueError('VCD time moved backwards')
                timestamp = now
                positive_time |= now > 0
            elif line and line[0] in '01xXzZbB':
                if line[0] in 'bB':
                    value, code = line[1:].split()
                else:
                    value, code = line[0], line[1:]
                if code in observations and not re.search('[xXzZ]', value):
                    # Store at most two known values per identifier: enough to
                    # establish observation/change without retaining a trace.
                    if len(observations[code]) < 2:
                        observations[code].add(int(value, 2))
    if not header_done or not timescale_lines or in_timescale or not positive_time:
        raise ValueError('VCD lacks complete definitions, timescale or advancing time')
    for name in required:
        if not observations[declarations[name][1]]:
            raise ValueError(f'No known value recorded for {name}')
    for name in ('clk', 'rst', 'in_valid', 'out_valid'):
        if observations[declarations[name][1]] != {0, 1}:
            raise ValueError(f'No high/low observations for {name}')
    if len(observations[declarations['x'][1]]) < 2:
        raise ValueError('No input data changes recorded')
    return dict(timescale=' '.join(timescale_lines), final_timestamp=timestamp,
                required_signals={name: dict(width=width, identifier=declarations[name][1])
                                  for name, width in required.items()},
                bytes=Path(path).stat().st_size,
                scope='Recording observability only; no activity counts or window validation')


def check(run, n=8):
    run = Path(run).resolve()
    if n < 2:
        raise ValueError('Use at least two vectors to observe input changes')
    for tool in ('iverilog', 'vvp'):
        if not shutil.which(tool):
            raise RuntimeError(f'{tool} is required for this recording check')
    attempt = Path(tempfile.mkdtemp(prefix='waveform-check.', dir=run))
    result = dict(status='running', attempt=str(attempt), n_vectors=n,
                  scope='Step 3.2 short core recording smoke; not full baseline capture, '
                        'UART, routed-delay, switching-rate, power or energy evidence',
                  nominal_clock_mhz=100, records=[])
    report = attempt / 'result.json'
    report.write_text(json.dumps(result, indent=2) + '\n')
    try:
        net = hard.load(run / 'model.json')
        all_x = np.load(run / 'x_test_bits.npy')
        if n > len(all_x):
            raise ValueError('Requested more vectors than saved inputs')
        x = all_x[:n]
        result['input_order'] = f'First {n} rows, unchanged saved order'
        provenance = [run / 'model.json', run / 'x_test_bits.npy',
                      ROOT / 'dlgn/export_verilog.py', ROOT / 'dlgn/hard.py',
                      ROOT / 'dlgn/gates.py', ROOT / 'sim/run_sim.sh', Path(__file__).resolve()]
        result['source_sha256'] = {str(p): digest(p) for p in provenance}
        result['simulators'] = {}
        for tool in ('iverilog', 'vvp'):
            path = Path(shutil.which(tool)).resolve()
            version = subprocess.run([str(path), '-V'], capture_output=True, text=True, check=True)
            result['simulators'][tool] = dict(path=str(path), sha256=digest(path),
                                              version=version.stdout + version.stderr)
        files = ('dlgn_top.sv', 'tb_dlgn.sv', 'x.hex', 'exp_scores.hex', 'exp_class.hex', 'params.json')
        for architecture, head in (('comb', False), ('comb_head', True)):
            mode_hashes = []
            for recording in (False, True):
                folder = attempt / f'{architecture}_dump_{int(recording)}'
                params = export(net, x, str(folder), head_pipeline=head)
                (folder / 'params.json').write_text(json.dumps(params, indent=2) + '\n')
                env = os.environ.copy()
                env.pop('DUMP', None)
                env['SIM'] = 'iverilog'
                if recording:
                    env['DUMP'] = '1'
                command = ['bash', str(ROOT / 'sim/run_sim.sh'), str(folder)]
                (folder / 'command.json').write_text(json.dumps(dict(command=command,
                    environment=dict(SIM='iverilog', DUMP='1' if recording else None)), indent=2) + '\n')
                process = subprocess.run(command, env=env, capture_output=True, text=True, timeout=120)
                (folder / 'stdout.log').write_text(process.stdout)
                (folder / 'stderr.log').write_text(process.stderr)
                expected = f'PASS: {n}/{n} vectors bit-exact (scores + class)'
                if process.returncode or expected not in process.stdout or re.search(r'^(FAIL|MISMATCH)', process.stdout, re.M):
                    raise RuntimeError(f'Simulation failed; see {folder}')
                vcd = folder / 'dlgn.vcd'
                if vcd.exists() != recording:
                    raise ValueError(f'Unexpected waveform presence/absence: {folder}')
                observation = inspect_vcd(vcd, params) if recording else None
                hashes = {name: digest(folder / name) for name in files}
                mode_hashes.append(hashes)
                saved = files + ('command.json', 'stdout.log', 'stderr.log', 'sim.log')
                if recording:
                    saved += ('dlgn.vcd',)
                result['records'].append(dict(architecture=architecture, recording=recording,
                    folder=str(folder), passed_vectors=n, params=params, waveform=observation,
                    files_sha256={name: digest(folder / name) for name in saved}))
            if mode_hashes[0] != mode_hashes[1]:
                raise ValueError(f'Recording modes used different sources/vectors: {architecture}')
        result['status'] = 'passed'
    except Exception as exc:
        result.update(status='failed', error=str(exc))
        raise
    finally:
        report.write_text(json.dumps(result, indent=2) + '\n')
        print(f'Recording-check evidence: {report}', flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--n', type=int, default=8)
    args = parser.parse_args()
    check(args.run, args.n)
