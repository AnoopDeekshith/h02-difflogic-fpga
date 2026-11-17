"""Step 3.7: compare settled RTL values and changes with the NumPy reference.

Reanalyse archived captures, with matched image order and per-stage windows.
Recorded intermediate events remain distinct from settled logical changes.
This is not mapped activity, physical glitches, power, energy or novelty.
"""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
from dlgn import hard  # noqa: E402
from dlgn.export_verilog import emit_rtl  # noqa: E402
from dlgn.vcd_activity import analyze_vcd  # noqa: E402
from analyze_waveform import digest  # noqa: E402
from report_activity_windows import validate_windows, _snapshots, _known  # noqa: E402


def pack_bits(rows):
    """Column j is Verilog bit j, including widths not divisible by eight."""
    return [int.from_bytes(row.tobytes(), 'little') for row in
            np.packbits(rows, axis=1, bitorder='little')]


def reference_values(capture, params, n):
    net = hard.load(capture/'model.json')
    inputs = np.load(capture/'x_test_bits.npy', allow_pickle=False)
    if inputs.shape != (n, params['IN']) or inputs.dtype.kind not in 'bui' or not np.all(
            (inputs == 0) | (inputs == 1)):
        raise ValueError('Expected binary NumPy inputs with the archived image count/width')
    previous = params['IN']
    for index, layer in enumerate(net['layers'], 1):
        for field, limit in (('ia', previous), ('ib', previous), ('gates', 16)):
            values = layer[field]
            if len(values) != params['W'] or any(type(v) is not int or not 0 <= v < limit for v in values):
                raise ValueError(f'Invalid model layer {index} {field}')
        previous = params['W']
    layers = hard.forward_bits(net, inputs)
    scores = hard.scores(net, inputs)
    classes = hard.predict(net, inputs)
    if len(layers) != params['D'] or scores.shape != (n, params['K']) or not np.array_equal(
            classes, scores.argmax(axis=1)):
        raise ValueError('NumPy reference shape or lowest-index argmax disagrees')
    words = pack_bits(inputs)
    score_words = [sum(int(value) << (k*params['SW']) for k, value in enumerate(row)) for row in scores]
    class_words = [int(v) for v in classes]
    for name, expected in [('x.hex', words), ('exp_scores.hex', score_words), ('exp_class.hex', class_words)]:
        if [int(s, 16) for s in (capture/name).read_text().split()] != expected:
            raise ValueError(f'Archived {name} disagrees with fresh NumPy reference/order')
    refs = dict(x=words, l0=words, scores=score_words, sc_flat=score_words,
                best=class_words, class_out=class_words)
    for d, layer in enumerate(layers, 1):
        refs[f'l{d}_c'] = refs[f'l{d}'] = pack_bits(layer)
    tied = np.sum(scores == scores.max(axis=1, keepdims=True), axis=1) > 1
    return refs, int(tied.sum())


def settled_stats(words, width):
    flips = rises = falls = 0
    masks = []
    for before, after in zip(words, words[1:]):
        change = before ^ after
        masks.append(change)
        flips += change.bit_count()
        rises += (change & after).bit_count()
        falls += (change & before).bit_count()
    opportunities = width*(len(words)-1)
    return dict(known_bit_toggles=flips, rises=rises, falls=falls,
                bit_pair_opportunities=opportunities,
                changes_per_bit_per_image_pair=flips/opportunities), masks


def compare_observations(capture, validated, refs):
    """Exact state and transition masks, not just aggregate toggle totals."""
    windows = validated['windows']
    period, n = validated['clock']['simulated_period_ps'], validated['n_images']
    required = {w['signal']: ['tb_capture', 'dut'] for w in windows}
    required.update({s: ['tb_capture', 'dut'] for s in ('clk', 'rst', 'in_valid', 'out_valid')})
    times = [w['first_sample_ps']+i*period for w in windows for i in range(n)]
    _, snapshots, *_ = _snapshots(capture/'dlgn.vcd', required, times)
    raw_windows, rows, evidence = {}, [], []
    for window in windows:
        name, width = window['signal'], window['width']
        times = [window['first_sample_ps']+i*period for i in range(n)]
        actual = [_known(snapshots[t], name) for t in times]
        expected = refs[name]
        rtl_stats, rtl_masks = settled_stats(actual, width)
        numpy_stats, numpy_masks = settled_stats(expected, width)
        mismatches = [i for i, (a, e) in enumerate(zip(actual, expected)) if a != e]
        pair_mismatches = [i for i, (a, e) in enumerate(zip(rtl_masks, numpy_masks)) if a != e]
        bounds = (window['start_exclusive_tick'], window['end_inclusive_tick'])
        if bounds not in raw_windows:
            raw = analyze_vcd(capture/'dlgn.vcd', *bounds)
            raw_windows[bounds] = {s['identifier']: s['counts'] for s in raw['signals']}
        recorded = raw_windows[bounds][window['identifier']]
        row = dict(**window, canonical_logical_output=bool(re.fullmatch(r'l[1-9]\d*_c', name)),
                   numpy=numpy_stats, rtl=rtl_stats,
                   mismatched_samples=len(mismatches), mismatched_sample_bits=sum(
                       (a ^ e).bit_count() for a, e in zip(actual, expected)),
                   mismatched_transition_pairs=len(pair_mismatches),
                   mismatched_transition_bits=sum((a ^ e).bit_count() for a, e in zip(rtl_masks, numpy_masks)),
                   first_mismatches=[dict(image_index=i, time_ps=times[i],
                       expected_hex=format(expected[i], 'x'), actual_hex=format(actual[i], 'x'),
                       differing_bit_indices=[j for j in range(width) if ((actual[i] ^ expected[i]) >> j) & 1])
                       for i in mismatches[:8]],
                   recorded=recorded,
                   recorded_minus_settled_known_changes=recorded['known_bit_toggles']-rtl_stats['known_bit_toggles'],
                   recorded_interpretation=(
                       'X/Z events exist between known samples; known-event counts alone omit unknown-involving changes'
                       if recorded['unknown_bit_changes'] else
                       'Recorded and settled counts agree in this observation window; no physical-glitch inference'
                       if recorded['known_bit_toggles'] == rtl_stats['known_bit_toggles'] else
                       'Additional recorded intermediate events; these are simulator events, not physical glitches'))
        if row['canonical_logical_output']:
            row['per_gate_numpy_changes'] = [sum((mask >> j) & 1 for mask in numpy_masks) for j in range(width)]
            row['per_gate_rtl_changes'] = [sum((mask >> j) & 1 for mask in rtl_masks) for j in range(width)]
        rows.append(row)
        evidence.append(dict(signal=name, width=width, sample_times_ps=times,
                             numpy_hex=[format(v, 'x') for v in expected],
                             rtl_hex=[format(v, 'x') for v in actual]))
    canonical = [r for r in rows if r['canonical_logical_output']]
    if len(canonical) != validated['architecture']['D'] or len({r['identifier'] for r in canonical}) != len(canonical):
        raise ValueError('Canonical layers must have separate identifiable observations')
    total = {k: sum(r['rtl'][k] for r in canonical) for k in ('known_bit_toggles', 'rises', 'falls', 'bit_pair_opportunities')}
    total['changes_per_gate_per_image_pair'] = total['known_bit_toggles']/total['bit_pair_opportunities']
    return dict(observations=rows, logical_gate_output_metric=total,
                matched_observations=sum(r['mismatched_samples'] == 0 for r in rows),
                compared_sample_bits=sum(r['width']*n for r in rows),
                compared_transition_bits=sum(r['width']*(n-1) for r in rows),
                mismatch_count=sum(r['mismatched_samples'] for r in rows)), evidence


def compare_activity(capture):
    capture = Path(capture).resolve()
    output = Path(tempfile.mkdtemp(prefix='activity-numpy.', dir=capture))
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
        sources = [Path(__file__).resolve(), ROOT/'scripts/report_activity_windows.py',
                   ROOT/'scripts/analyze_waveform.py', ROOT/'scripts/capture_baseline_waveform.py',
                   ROOT/'dlgn/vcd_activity.py', ROOT/'dlgn/export_verilog.py',
                   ROOT/'dlgn/gates.py', ROOT/'dlgn/hard.py']
        (output/'capture-manifest.json').write_bytes(original)
        for source in sources:
            shutil.copyfile(source, output/source.name)
        source_hashes = {str(p): digest(p) for p in sources}
        result.update(capture_directory=str(capture), capture_report_sha256=hashlib.sha256(original).hexdigest(),
                      capture_artifacts_sha256=hashes, source_sha256=source_hashes,
                      analysis_artifacts_sha256={p.name: digest(output/p.name) for p in sources},
                      environment=dict(python=platform.python_version(), numpy=np.__version__))
        result['analysis_artifacts_sha256']['capture-manifest.json'] = digest(output/'capture-manifest.json')
        params, n = manifest['params'], manifest['n_images']
        pipeline = params['LAT'] == params['D']+2+int(params['head_pipeline'])
        rtl, emitted = emit_rtl(hard.load(capture/'model.json'), pipeline=pipeline,
                                head_pipeline=params['head_pipeline'])
        if emitted != params or rtl != (capture/'dlgn_top.sv').read_text():
            raise ValueError('Archived RTL/parameters differ from the supported exporter architecture')
        refs, ties = reference_values(capture, params, n)
        validated = validate_windows(capture, manifest)
        comparison, evidence = compare_observations(capture, validated, refs)
        (output/'settled-values.json').write_text(json.dumps(evidence, separators=(',', ':'))+'\n')
        result['analysis_artifacts_sha256']['settled-values.json'] = digest(output/'settled-values.json')
        result.update(n_images=n, architecture=params, clock=validated['clock'],
                      windows=validated['windows'], window_policy=validated['window_policy'],
                      checks=dict(**validated['checks'], numpy_inputs_and_hex_order_verified=True,
                                  numpy_score_class_references_verified=True,
                                  tie_breaking='lowest class index', tied_score_images=ties),
                      **comparison,
                      limits=['Exact sampled-workload comparison, not formal equivalence over all inputs',
                              'Only l1_c..lD_c contribute to the logical comparison metric; copies excluded',
                              'Recorded events and X/Z changes remain separate from settled known-state differences',
                              'Per-stage aligned image pairs do not form a shared physical energy interval',
                              'No mapped activity, physical glitches, power/energy benefit or novelty established',
                              'Historical inspected digits baseline remains exploratory; no retraining or selection'])
        if original != (capture/'result.json').read_bytes() or any(
                digest(capture/name) != expected for name, expected in hashes.items()) or any(
                digest(p) != h for p, h in source_hashes.items()):
            raise ValueError('Capture or comparison source changed during analysis')
        if comparison['mismatch_count']:
            raise ValueError(f'NumPy/RTL settled value mismatch in {comparison["mismatch_count"]} observation samples')
        if any(r['mismatched_transition_pairs'] or r['numpy'] != r['rtl'] or
               r.get('per_gate_numpy_changes') != r.get('per_gate_rtl_changes') for r in comparison['observations']):
            raise ValueError('NumPy/RTL settled transition mismatch')
        result['checks']['logical_layer_numpy_comparison'] = True
        result['checks']['all_observation_values_and_transition_masks_match'] = True
        result['status'] = 'passed'
    except Exception as exc:
        result.update(status='failed', error=str(exc))
        raise
    finally:
        destination.write_text(json.dumps(result, indent=2)+'\n')
        print(f'NumPy/RTL activity evidence: {destination}', flush=True)
    return result


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('capture', type=Path)
    compare_activity(ap.parse_args().capture)
