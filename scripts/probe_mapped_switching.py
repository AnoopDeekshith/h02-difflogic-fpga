"""Step 4.13: screening probe of mapped core switching for one matched pair.

For a control and a lambda-0.3 diagnostic model (same model seed), export the
feasible head-only core with the saved validation images, check RTL and the
zero-delay iCE40 mapped netlist bit for bit against NumPy, then count core-net
transitions (M1 raw, M2 fanout-weighted) and apply the frozen PAUSE/CONTINUE
probe rule. Test data are never loaded. This is a switching proxy, not power,
energy, glitch or routed-timing evidence.

  python scripts/probe_mapped_switching.py CONTROL_RUN PENALTY_RUN \
      --policy docs/experiments/hardware-switching-stop-rule-v3.json
"""
import argparse
import hashlib
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
from dlgn.export_verilog import export  # noqa: E402
from capture_baseline_waveform import validate_events, write_parameters, HALF_PERIOD_PS  # noqa: E402
from mapped_activity import port_widths, instrument_json, count_activity, validate_port_bus  # noqa: E402

CORE_CATEGORIES = ('lut', 'carry', 'ff')
POLICY_SCHEMA = 'hardware_switching_stop_rule_v3'
POLICY_SHA256 = '5d22135a5caa14e258c48aa386c5a41e2fba359cca12c733ac1b7e3b7236930d'
RUN_FILES = ('model.json', 'metrics.json', 'protocol.json', 'split_indices.npz',
             'x_validation_bits.npy', 'y_validation.npy',
             'validation_scores.npy', 'validation_classes.npy')
SOURCE_FILES = ('scripts/probe_mapped_switching.py', 'scripts/mapped_activity.py',
                'scripts/capture_baseline_waveform.py', 'rtl/tb_mapped_capture.sv',
                'dlgn/hard.py', 'dlgn/gates.py', 'dlgn/export_verilog.py',
                'dlgn/vcd_activity.py', 'sim/run_sim.sh')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fanout(entry):
    """Number of mapped cell input-pin bits a net drives.

    Ledger `users` lists every connection, including the net's own driver and
    top-level port references; only cell input pins count as load.
    """
    loads = [u for u in entry['users']
             if not u.startswith('port:') and u != entry['driver']]
    if any(u.startswith('primary:') for u in loads):
        raise ValueError(f'Unexpected primary reference in users of {entry["bit_id"]}')
    return len(loads)


def core_metrics(ledger, activity):
    """M1/M2 over nets driven by core LUT, carry and flip-flop cells."""
    entries, per_bit = ledger['entries'], activity['per_bit']
    if len(entries) != len(per_bit):
        raise ValueError('Ledger and activity widths differ')
    m1 = m2 = unknown = nets = 0
    by_category = {c: dict(nets=0, M1=0, M2=0) for c in CORE_CATEGORIES}
    for entry, counts in zip(entries, per_bit):
        if entry['category'] not in CORE_CATEGORIES:
            continue
        load = fanout(entry)
        toggles = counts['known_toggles']
        nets += 1
        m1 += toggles
        m2 += toggles*load
        unknown += counts['unknown_changes']
        row = by_category[entry['category']]
        row['nets'] += 1
        row['M1'] += toggles
        row['M2'] += toggles*load
    return dict(core_nets=nets, M1=m1, M2=m2, unknown_changes=unknown,
                by_category=by_category)


def load_policy(path):
    """Load the frozen stop rule; reject any other schema or content."""
    path = Path(path).resolve()
    policy = json.loads(path.read_text())
    if policy.get('schema') != POLICY_SCHEMA or digest(path) != POLICY_SHA256:
        raise ValueError('The probe requires the frozen v3 stop-rule policy')
    return path, policy


def check_frozen_models(policy, seed, control, penalty):
    """Run folders and model.json hashes must equal the policy's frozen list."""
    frozen = policy['models'][f'seed_{seed}']
    for role, run in (('control', control), ('penalty', penalty)):
        if Path(run).resolve() != (ROOT/frozen[role]).resolve() or (
                digest(Path(run)/'model.json') != frozen[f'{role}_model_sha256']):
            raise ValueError(f'{role} run/model differs from the frozen policy list')


def window_bounds(events):
    """Standalone-core window (first drive - half period - 1 ps, last output check]."""
    return events['first_input_ps'] - HALF_PERIOD_PS - 1, events['last_output_check_ps']


def reduction(control, penalty):
    if not control > 0:
        raise ValueError('Control metric must be positive to form a reduction')
    return 1.0 - penalty/control


def probe_decision(r1, r2, threshold_percent):
    """Frozen probe rule: PAUSE only if both reductions are below threshold."""
    limit = threshold_percent/100.0
    return 'PAUSE' if (r1 < limit and r2 < limit) else 'CONTINUE'


def _run(command, folder, log, timeout=600):
    proc = subprocess.run(command, cwd=folder, capture_output=True, text=True, timeout=timeout)
    (Path(folder)/log).write_text(proc.stdout + proc.stderr)
    if proc.returncode:
        raise RuntimeError(f'Command failed ({proc.returncode}); see {Path(folder)/log}')
    return proc.stdout


def _tool(name, sibling=None):
    path = Path(sibling).parent/name if sibling else shutil.which(name)
    if not path or not Path(path).is_file():
        raise RuntimeError(f'{name} is required')
    return str(Path(path).resolve())


def tools():
    yosys, iverilog = _tool('yosys'), _tool('iverilog')
    found = dict(yosys=yosys, yosys_config=_tool('yosys-config', yosys),
                 iverilog=iverilog, vvp=_tool('vvp', iverilog))
    versions = {k: subprocess.run([v, '-V'] if k != 'yosys_config' else [v, '--version'],
                                  capture_output=True, text=True).stdout.strip().splitlines()[:1]
                for k, v in found.items()}
    return found, versions


def check_run(run, expected_lambda, expected_seed):
    """Bind a model to its archived validation-only training manifest."""
    run = Path(run).resolve()
    status = json.loads((run/'status.json').read_text())
    if status.get('status') != 'passed' or digest(run/'manifest.json') != status['manifest_sha256']:
        raise ValueError(f'{run}: training status/manifest check failed')
    manifest = json.loads((run/'manifest.json').read_text())
    for name in RUN_FILES:
        if digest(run/name) != manifest['files_sha256'][name]:
            raise ValueError(f'{run}: {name} differs from manifest')
    if (run/'x_test_bits.npy').exists():
        raise ValueError(f'{run}: unexpected test export in a deferred-test run')
    metrics = json.loads((run/'metrics.json').read_text())
    args = metrics['args']
    if (metrics.get('test_evaluated') is not False or not args.get('defer_test')
            or args['seed'] != expected_seed or args['split_seed'] != 0
            or float(args['act_weight']) != float(expected_lambda)
            or (expected_lambda and args['act_mode'] != 'batch')):
        raise ValueError(f'{run}: unexpected protocol/seed/lambda')
    return run, metrics, manifest


def capture_model(run, folder, policy):
    """Export, RTL-check, map, mapped-check and count one model."""
    folder.mkdir()
    net = hard.load(str(run/'model.json'))
    x = np.load(run/'x_validation_bits.npy')
    sc = hard.scores(net, x)
    if not (np.array_equal(sc, np.load(run/'validation_scores.npy'))
            and np.array_equal(sc.argmax(1), np.load(run/'validation_classes.npy'))):
        raise ValueError('Fresh NumPy validation scores/classes differ from archive')
    n = len(x)
    rtl = folder/'rtl'
    params = export(net, x, str(rtl), pipeline=False, head_pipeline=True)
    (rtl/'params.json').write_text(json.dumps(params, indent=2)+'\n')
    if params['LAT'] != 3:
        raise ValueError('Expected the feasible head-only core (LAT 3)')
    _run(['bash', str(ROOT/'sim/run_sim.sh'), str(rtl)], rtl, 'run_sim.stdout.log')
    rtl_log = (rtl/'sim.log').read_text()
    if f'PASS: {n}/{n} vectors bit-exact (scores + class)' not in rtl_log:
        raise ValueError('RTL simulation did not report a complete pass')

    mapped_dir = folder/'mapped'
    mapped_dir.mkdir()
    for name in ('dlgn_top.sv', 'x.hex', 'exp_scores.hex', 'exp_class.hex'):
        shutil.copyfile(rtl/name, mapped_dir/name)
    shutil.copyfile(ROOT/'rtl/tb_mapped_capture.sv', mapped_dir/'tb_mapped_capture.sv')
    write_parameters(mapped_dir, params, n)
    found, _ = tools()
    datdir = subprocess.check_output([found['yosys_config'], '--datdir'], text=True).strip()
    shutil.copyfile(Path(datdir)/'ice40/cells_sim.v', mapped_dir/'cells_sim.v')
    commands = [
        [found['yosys'], '-Q', '-l', 'synth.log', '-p',
         'read_verilog -sv dlgn_top.sv; synth_ice40 -device u -top dlgn_top -json mapped.json; stat'],
        [found['yosys'], '-Q', '-l', 'write.log', '-p',
         'read_json instrumented.json; write_verilog -noattr mapped_core.v'],
        [found['iverilog'], '-g2012', '-s', 'tb_capture', '-o', 'simv',
         'tb_mapped_capture.sv', 'mapped_core.v', 'cells_sim.v'],
        [found['vvp'], 'simv']]
    (mapped_dir/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
    _run(commands[0], mapped_dir, 'synth.stdout.log')
    mapped = json.loads((mapped_dir/'mapped.json').read_text())
    instrumented, ledger = instrument_json(mapped, port_widths(params))
    (mapped_dir/'instrumented.json').write_text(json.dumps(instrumented, sort_keys=True)+'\n')
    (mapped_dir/'net-ledger.json').write_text(json.dumps(ledger, indent=2)+'\n')
    _run(commands[1], mapped_dir, 'write.stdout.log')
    _run(commands[2], mapped_dir, 'build.log')
    _run(commands[3], mapped_dir, 'sim.log')
    if f'PASS: {n}/{n} mapped vectors bit-exact (scores + class)' not in (mapped_dir/'sim.log').read_text():
        raise ValueError('Missing complete mapped score/class pass')
    events = validate_events(mapped_dir/'events.csv', n, params)
    port_check = validate_port_bus(mapped_dir/'mapped.vcd', mapped, ledger)
    window = policy['fixed_setup']['window']['standalone_core']
    start, end = window_bounds(events)
    activity = count_activity(mapped_dir/'mapped.vcd', ledger, start, end)
    if activity['max_bus_records_per_tick'] != 1:
        raise ValueError('Expected one canonical bus record per timestamp')
    metrics = core_metrics(ledger, activity)
    if metrics['unknown_changes'] or activity['totals'].get('initial_unknown_bits', 0):
        raise ValueError('Unknown values inside the measurement window')
    summary = dict(
        n_images=n, params=params, rtl_pass=True, mapped_pass=True,
        primitive_counts=ledger['primitive_counts'],
        category_bit_counts=ledger['category_bits'],
        event_ledger=events, port_bus_check=port_check,
        window=dict(start_exclusive_ps=start, end_inclusive_ps=end, definition=window),
        metrics=metrics, commands=commands)
    (mapped_dir/'vcd_size_bytes').write_text(str((mapped_dir/'mapped.vcd').stat().st_size)+'\n')
    (mapped_dir/'mapped.vcd').unlink()  # large; regenerable from archived sources
    (mapped_dir/'simv').unlink()
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('control')
    ap.add_argument('penalty')
    ap.add_argument('--policy', required=True)
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--penalty-lambda', type=float, default=0.3)
    ap.add_argument('--out-parent', default=str(ROOT/'runs'))
    a = ap.parse_args()

    policy_path, policy = load_policy(a.policy)
    if a.seed != 1 or a.penalty_lambda != 0.3:
        raise ValueError('The frozen probe uses model seed 1 and lambda 0.3')
    control, control_metrics, _ = check_run(a.control, 0.0, a.seed)
    penalty, penalty_metrics, _ = check_run(a.penalty, a.penalty_lambda, a.seed)
    check_frozen_models(policy, a.seed, control, penalty)
    if not np.array_equal(np.load(control/'x_validation_bits.npy'), np.load(penalty/'x_validation_bits.npy')):
        raise ValueError('Control and penalty validation workloads differ')

    folder = Path(tempfile.mkdtemp(prefix='step4.13-probe.', dir=a.out_parent))
    report = folder/'result.json'
    sources = {s: digest(ROOT/s) for s in SOURCE_FILES}
    found, versions = tools()
    plan = dict(step='4.13', policy=str(policy_path), policy_sha256=digest(policy_path),
                control=str(control), penalty=str(penalty), seed=a.seed,
                penalty_lambda=a.penalty_lambda, source_sha256=sources,
                tools=found, tool_versions=versions,
                note='Written before any capture in this folder.')
    (folder/'plan.json').write_text(json.dumps(plan, indent=2)+'\n')
    result = dict(status='running', directory=str(folder))
    report.write_text(json.dumps(result, indent=2)+'\n')
    try:
        models = {}
        for name, run in (('control', control), ('penalty', penalty)):
            models[name] = capture_model(run, folder/name, policy)
        cm, pm = models['control']['metrics'], models['penalty']['metrics']
        r1, r2 = reduction(cm['M1'], pm['M1']), reduction(cm['M2'], pm['M2'])
        threshold = policy['threshold_percent']
        decision = probe_decision(r1, r2, threshold)
        if {s: digest(ROOT/s) for s in SOURCE_FILES} != sources or digest(policy_path) != plan['policy_sha256']:
            raise ValueError('Source or policy changed during the probe')
        logical = {k: dict(changes=m['validation']['changes'], rate=m['validation']['ref_toggle_rate'],
                           validation_accuracy=m['validation']['ref_acc'])
                   for k, m in (('control', control_metrics), ('penalty', penalty_metrics))}
        result.update(
            status='passed', decision=decision, threshold_percent=threshold,
            reductions=dict(M1=r1, M2=r2,
                            logical_settled=reduction(logical['control']['changes'],
                                                      logical['penalty']['changes'])),
            logical_reference=logical, models=models,
            label='lambda 0.3 is an accuracy-failed hardware diagnostic, not a selected model',
            limits=['Zero-delay mapped standalone core; no routing, glitches, power or energy',
                    'One model seed; screening only, not the final 4.14 decision',
                    'Fanout-weighted counts are a rough capacitance stand-in'])
    except Exception as exc:
        result.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        report.write_text(json.dumps(result, indent=2, default=str)+'\n')
        print(f'Probe evidence: {report}', flush=True)


if __name__ == '__main__':
    main()
