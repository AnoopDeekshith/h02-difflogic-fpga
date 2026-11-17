"""Step 3.6: separate observable RTL activity; no physical power model.

Whole-trace categories partition VCD identifiers, not physical FPGA nets.
Frame-aligned observations distinguish recorded events from settled changes.
Only l1_c..lD_c contribute to the logical gate-output comparison metric.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
from dlgn.export_verilog import emit_rtl  # noqa: E402
from dlgn.vcd_activity import COUNT_FIELDS, analyze_vcd  # noqa: E402
from analyze_waveform import digest  # noqa: E402
from report_activity_windows import validate_windows, _snapshots, _known  # noqa: E402


def alias_category(alias, params):
    """Roles come from the checked exporter architecture, never VCD reg type."""
    scope, name = alias['scope'], alias['reference']
    pipeline = params['LAT'] == params['D']+2+int(params['head_pipeline'])
    if scope == ['tb_capture']:
        return 'testbench'
    if scope[:2] != ['tb_capture', 'dut']:
        raise ValueError(f'Unclassified scope: {alias["path"]}')
    if len(scope) > 2:
        if len(scope) == 3 and scope[2].startswith('$ivl_for_loop') and name == 'k':
            return 'simulator_bookkeeping'
        raise ValueError(f'Unclassified nested signal: {alias["path"]}')
    if name == 'clk':
        return 'clock'
    if name in ('rst', 'in_valid', 'out_valid', 'vpipe'):
        return 'control'
    if name == 'x':
        return 'input_port'
    if name in ('l0', 'scores', 'class_out'):
        return 'data_register'
    match = re.fullmatch(r'l([1-9]\d*)(_c)?', name)
    if match and int(match[1]) <= params['D']:
        return ('logical_layer_output' if match[2] else
                'layer_register' if pipeline else 'logical_layer_copy')
    if name == 'sc_flat':
        return 'head_score_register_view' if params['head_pipeline'] else 'output_logic'
    if name in ('best', 'best_sc') or re.fullmatch(r'pc\d+_d\d+_\d+|win_\d+_\d+_[sc]', name):
        return 'output_logic'
    if name == 'LATENCY':
        return 'elaboration_constant'
    raise ValueError(f'Unclassified DUT signal: {alias["path"]}')


def partition_activity(analysis, params):
    """Each ID belongs once. Equal values on different IDs remain distinct."""
    groups, rows = {}, []
    for signal in analysis['signals']:
        roles = {alias_category(a, params) for a in signal['aliases']}
        # A testbench port alias is the same ID, not a second observed net.
        owned = roles-{'testbench'} if len(roles) > 1 else roles
        # A wire-only layer forwarding alias may share its producer's ID.
        if owned == {'logical_layer_output', 'logical_layer_copy'}:
            owned = {'logical_layer_output'}
        if len(owned) != 1:
            raise ValueError(f'Ambiguous cross-category alias ID {signal["identifier"]}: {roles}')
        category = next(iter(owned))
        group = groups.setdefault(category, dict(identifier_count=0, declared_bits=0,
                                                 counts={k: 0 for k in COUNT_FIELDS}))
        group['identifier_count'] += 1
        group['declared_bits'] += signal['width']
        for key in COUNT_FIELDS:
            group['counts'][key] += signal['counts'][key]
        rows.append(dict(**signal, category=category, alias_roles=sorted(roles)))
    totals = {k: sum(g['counts'][k] for g in groups.values()) for k in COUNT_FIELDS}
    if totals != analysis['totals'] or sum(g['identifier_count'] for g in groups.values()) != analysis['unique_identifier_count']:
        raise ValueError('Category accounting does not reconcile')
    return dict(window=analysis['window'], categories=groups, signals=rows,
                unique_identifier_count=analysis['unique_identifier_count'],
                declaration_count=analysis['declaration_count'], totals=totals,
                reconciled=True,
                interpretation='Whole trace including reset/fill/drain; a partition of recorded IDs, '
                               'not unique physical nodes or useful-work network switching')


def aligned_observations(path, validated):
    windows, params = validated['windows'], validated['architecture']
    period = validated['clock']['simulated_period_ps']
    n = validated['n_images']
    names = {w['signal']: ['tb_capture', 'dut'] for w in windows}
    names.update({s: ['tb_capture', 'dut'] for s in ('clk', 'rst', 'in_valid', 'out_valid')})
    times = [w['first_sample_ps']+i*period for w in windows for i in range(n)]
    selected, saved, *_ = _snapshots(path, names, times)
    by_window, rows = {}, []
    for window in windows:
        bounds = (window['start_exclusive_tick'], window['end_inclusive_tick'])
        if bounds not in by_window:
            analysis = analyze_vcd(path, *bounds)
            by_window[bounds] = {s['identifier']: s for s in analysis['signals']}
        name = window['signal']
        identifier = selected[name]['identifier']
        values = [_known(saved[window['first_sample_ps']+i*period], name) for i in range(n)]
        toggles = rises = falls = 0
        for previous, current in zip(values, values[1:]):
            changed = previous ^ current
            toggles += changed.bit_count()
            rises += (changed & current).bit_count()
            falls += (changed & previous).bit_count()
        denominator = window['width']*(n-1)
        rows.append(dict(**window,
                         role=alias_category(dict(scope=['tb_capture', 'dut'], reference=name,
                                                  path='tb_capture.dut.'+name), params),
                         canonical_logical_output=bool(re.fullmatch(r'l[1-9]\d*_c', name)),
                         recorded=by_window[bounds][identifier]['counts'],
                         settled=dict(known_bit_toggles=toggles, rises=rises, falls=falls,
                                      bit_pair_opportunities=denominator,
                                      changes_per_bit_per_image_pair=toggles/denominator)))
    canonical = [r for r in rows if r['canonical_logical_output']]
    if len(canonical) != params['D'] or len({r['identifier'] for r in canonical}) != len(canonical):
        raise ValueError('Logical layer observations must be separately identifiable')
    flips = sum(r['settled']['known_bit_toggles'] for r in canonical)
    opportunities = sum(r['settled']['bit_pair_opportunities'] for r in canonical)
    return dict(observations=rows,
                logical_gate_output_metric=dict(signals=[r['signal'] for r in canonical],
                    known_bit_toggles=flips, bit_pair_opportunities=opportunities,
                    adjacent_image_pairs=n-1,
                    changes_per_gate_per_image_pair=flips/opportunities,
                    interpretation='Settled learned gate outputs counted once per logical slot; '
                                   'excludes lN copies/registers, ports, head, clock and control; '
                                   'not a physical total; NumPy layer comparison remains step 3.7'))


def report_categories(capture):
    capture = Path(capture).resolve()
    output = Path(tempfile.mkdtemp(prefix='activity-categories.', dir=capture))
    destination = output/'result.json'
    result = dict(status='running', directory=str(output), scope=__doc__.strip())
    try:
        original = (capture/'result.json').read_bytes()
        manifest = json.loads(original)
        if manifest.get('status') != 'passed':
            raise ValueError('Expected a passed full-capture manifest')
        hashes = manifest['files_sha256']
        required = {'dlgn.vcd', 'model.json', 'x_test_bits.npy', 'params.json',
                    'input_indices.json', 'events.csv', 'dlgn_top.sv', 'tb_activity_capture.sv',
                    'x.hex', 'exp_scores.hex', 'exp_class.hex'}
        if not required <= hashes.keys():
            raise ValueError('Missing required capture hashes')
        for name, expected in hashes.items():
            if Path(name).name != name or digest(capture/name) != expected:
                raise ValueError(f'Capture artifact changed or unsafe name: {name}')
        params = manifest['params']
        pipeline = params['LAT'] == params['D']+2+int(params['head_pipeline'])
        rtl, emitted = emit_rtl(json.loads((capture/'model.json').read_text()),
                                pipeline=pipeline, head_pipeline=params['head_pipeline'])
        if emitted != params or rtl != (capture/'dlgn_top.sv').read_text():
            raise ValueError('Archived RTL/parameters differ from the supported exporter architecture')
        validated = validate_windows(capture, manifest)
        whole = partition_activity(analyze_vcd(capture/'dlgn.vcd'), params)
        aligned = aligned_observations(capture/'dlgn.vcd', validated)
        if original != (capture/'result.json').read_bytes() or any(
                digest(capture/name) != expected for name, expected in hashes.items()):
            raise ValueError('Capture changed during category analysis')
        (output/'capture-manifest.json').write_bytes(original)
        sources = [Path(__file__).resolve(), ROOT/'scripts/report_activity_windows.py',
                   ROOT/'scripts/analyze_waveform.py', ROOT/'scripts/capture_baseline_waveform.py',
                   ROOT/'dlgn/vcd_activity.py', ROOT/'dlgn/export_verilog.py',
                   ROOT/'dlgn/gates.py', ROOT/'dlgn/hard.py']
        for source in sources:
            shutil.copyfile(source, output/source.name)
        result.update(status='passed', capture_directory=str(capture),
                      capture_report_sha256=digest(capture/'result.json'),
                      capture_artifacts_sha256=hashes,
                      source_sha256={str(p): digest(p) for p in sources},
                      analysis_artifacts_sha256={p.name: digest(output/p.name) for p in sources},
                      n_images=validated['n_images'], architecture=params, clock=validated['clock'],
                      checks=validated['checks'], supported_exporter_architecture_verified=True,
                      whole_trace=whole, **aligned,
                      observability=['Unpacked sc/sc_reg arrays are not separately dumped by this capture',
                                     'sc_flat is a packed view of sc_reg when head_pipeline is enabled; '
                                     'its VCD reg type alone does not identify storage',
                                     'pc and winner-tree wires are observable output-logic views; '
                                     'different IDs can still represent redundant logical information'],
                      limits=['Only RTL recorded events and settled endpoint comparisons',
                              'Whole-trace partition includes startup/control/testbench and logical copies',
                              'Staggered aligned observations cannot form a shared physical-time total',
                              'No logical-layer NumPy comparison until 3.7; no mapped or physical glitch evidence',
                              'No power/energy benefit or novelty established; historical data are exploratory'])
        result['analysis_artifacts_sha256']['capture-manifest.json'] = digest(output/'capture-manifest.json')
    except Exception as exc:
        result.update(status='failed', error=str(exc))
        raise
    finally:
        destination.write_text(json.dumps(result, indent=2)+'\n')
        print(f'Activity-category evidence: {destination}', flush=True)
    return result


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('capture', type=Path)
    report_categories(ap.parse_args().capture)
