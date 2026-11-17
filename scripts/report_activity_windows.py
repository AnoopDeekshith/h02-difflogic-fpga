"""Step 3.5: validate frame-aligned windows for the fixed streaming capture.

Each observation uses N known settled states and N-1 adjacent-image intervals.
These staggered windows are not a single device-wide energy interval. No
transition totals or layer-versus-NumPy activity comparison are produced here.
"""
import argparse
import csv
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
from dlgn.vcd_activity import analyze_vcd, _Tokens, _header, _state  # noqa: E402
from analyze_waveform import digest  # noqa: E402
from capture_baseline_waveform import validate_events  # noqa: E402


def derive_windows(params, first_input_ps, n_images, half_period_ps=41667):
    """Derive availability from registers; first/last are post-update samples."""
    depth, stages = params['D'], params['LAT']
    head = int(params['head_pipeline'])
    if type(n_images) is not int or n_images < 2 or depth < 1 or half_period_ps < 2:
        raise ValueError('At least two images and a positive clock/depth are required')
    if stages == 2 + head:
        pipeline = False
    elif stages == depth + 2 + head:
        pipeline = True
    else:
        raise ValueError('Unsupported register architecture')
    period = 2*half_period_ps
    offsets = dict(x=-half_period_ps, l0=0)
    for d in range(1, depth+1):
        offsets[f'l{d}_c'] = (d-1)*period if pipeline else 0
        offsets[f'l{d}'] = d*period if pipeline else 0
    head_offset = (depth if pipeline else 0)*period + head*period
    offsets.update(sc_flat=head_offset, best=head_offset,
                   scores=(stages-1)*period, class_out=(stages-1)*period)
    rows = []
    for signal, offset in offsets.items():
        start = first_input_ps + offset + 1
        if start < 0:
            raise ValueError('Window begins before trace origin')
        end = start + (n_images-1)*period
        rows.append(dict(signal=signal, offset_from_input_ps=offset,
                         first_sample_ps=start, last_sample_ps=end,
                         start_exclusive_tick=start, end_inclusive_tick=end,
                         sample_count=n_images, adjacent_pairs=n_images-1,
                         duration_ps=end-start))
    return rows


def _snapshots(path, required, sample_times):
    """End-of-timestamp carried states at requested ticks, including quiet ticks.

    The public counter first validates the complete digital VCD. Reuse its
    declaration/value normalization for this sampler; independent tests use a
    separate decoder. No recorded events are collapsed into activity totals.
    """
    analysis = analyze_vcd(path)
    if analysis['timescale']['magnitude'] != 1 or analysis['timescale']['unit'] != 'ps':
        raise ValueError('This capture contract requires a 1 ps timescale')
    times = sorted(set(sample_times))
    if not times or times[0] < 0 or times[-1] > analysis['last_timestamp_tick']:
        raise ValueError('Sampling endpoints are outside recorded trace')
    with Path(path).open() as source:
        tokens = _Tokens(source)
        signals, _, _ = _header(tokens)
        selected = {}
        for name, scope in required.items():
            matches = [s for s in signals.values() if any(
                a['scope'] == scope and a['reference'] == name for a in s['aliases'])]
            if len(matches) != 1:
                raise ValueError(f'Missing or ambiguous signal {name}')
            selected[name] = matches[0]
        ids = {s['identifier'] for s in selected.values()}
        states, saved, position = {}, {}, 0
        rising, falling = [], []
        control_changes = {name: [] for name in ('rst', 'in_valid', 'out_valid', 'x')}
        clock_id = selected['clk']['identifier']
        timestamp = 0
        while (token := tokens.get()) is not None:
            if token == '$comment':
                tokens.block()
            elif token.startswith('#'):
                following = int(token[1:])
                while position < len(times) and times[position] < following:
                    saved[times[position]] = {name: states.get(s['identifier'])
                                              for name, s in selected.items()}
                    position += 1
                timestamp = following
            elif token.startswith('$'):
                continue  # Validated dumpvars/dumpall/$end tokens only.
            else:
                if token[0] in 'bB':
                    bits, identifier = token[1:], tokens.need()
                else:
                    bits, identifier = token[0], token[1:]
                if identifier not in ids:
                    continue
                value = _state(bits, signals[identifier]['width'], tokens)
                old = states.get(identifier)
                states[identifier] = value
                for name, changes in control_changes.items():
                    if identifier == selected[name]['identifier'] and old != value:
                        changes.append((timestamp, value))
                if identifier == clock_id and old is not None:
                    if old == (0, 0, 0) and value == (1, 0, 0):
                        rising.append(timestamp)
                    elif old == (1, 0, 0) and value == (0, 0, 0):
                        falling.append(timestamp)
        while position < len(times):
            saved[times[position]] = {name: states.get(s['identifier'])
                                      for name, s in selected.items()}
            position += 1
    return selected, saved, rising, falling, control_changes, analysis['last_timestamp_tick']


def _known(snapshot, signal):
    value = snapshot[signal]
    if value is None or value[1] or value[2]:
        raise ValueError(f'Unknown/unobserved sampled value for {signal}')
    return value[0]


def validate_windows(capture, manifest):
    capture = Path(capture)
    params, n, clock = manifest['params'], manifest['n_images'], manifest['clock']
    half = clock['half_period_ps']
    if clock['nominal_hz'] != 12_000_000 or half != 41667 or (
            clock['simulated_period_ps'] != 2*half or clock['precision_ps'] != 1):
        raise ValueError('Clock differs from the fixed capture protocol')
    if manifest['workload']['initiation_interval_cycles'] != 1:
        raise ValueError('Window policy requires consecutive inputs without bubbles')
    events = validate_events(capture/'events.csv', n, params, half)
    if events != manifest['events']:
        raise ValueError('Capture boundary metadata disagrees with ledger')
    if json.loads((capture/'params.json').read_text()) != params or (
            json.loads((capture/'input_indices.json').read_text()) != list(range(n))):
        raise ValueError('Archived parameters/row order disagree with capture')
    first = events['first_input_ps']
    period = 2*half
    if first != 7*half:
        raise ValueError('Input schedule must follow exactly three reset cycles')
    windows = derive_windows(params, first, n, half)
    controls = ('clk', 'rst', 'in_valid', 'out_valid')
    markers = ('input_index', 'output_index', 'input_count', 'output_count', 'capture_done')
    required = {w['signal']: ['tb_capture', 'dut'] for w in windows}
    required.update({s: ['tb_capture', 'dut'] for s in controls})
    required.update({s: ['tb_capture'] for s in markers})
    inputs = [int(s, 16) for s in (capture/'x.hex').read_text().split()]
    scores = [int(s, 16) for s in (capture/'exp_scores.hex').read_text().split()]
    classes = [int(s, 16) for s in (capture/'exp_class.hex').read_text().split()]
    if not (len(inputs) == len(scores) == len(classes) == n):
        raise ValueError('Reference vector count differs from window population')
    done, last_check = events['capture_done_ps'], events['last_output_check_ps']
    if done-last_check != 5*half-1:
        raise ValueError('Incorrect final three-falling-edge drain')
    times = [w['first_sample_ps']+i*period for w in windows for i in range(n)]
    times += [5*half, 6*half, done, first-half, last_check]
    times += [first+i*period for i in range(n)]
    selected, sampled, rising, falling, controls_seen, final = _snapshots(capture/'dlgn.vcd', required, times)
    for name, signal in selected.items():
        width = (1 if name in controls or name == 'capture_done' else
                 32 if name in markers else
                 params['IN'] if name in ('x', 'l0') else
                 params['K']*params['SW'] if name in ('sc_flat', 'scores') else
                 params['CW'] if name in ('best', 'class_out') else params['W'])
        if signal['width'] != width:
            raise ValueError(f'Unexpected declaration width for {name}')
    expected_rising = list(range(half, done+1, period))
    expected_falling = list(range(period, done+1, period))
    if rising != expected_rising or falling != expected_falling or final != done+1:
        raise ValueError('Clock cadence or recording tail differs from capture contract')
    if _known(sampled[5*half], 'rst') != 1 or _known(sampled[6*half], 'rst') != 0:
        raise ValueError('Reset does not cover the initial three cycles')
    if controls_seen['rst'] != [(0, (1, 0, 0)), (6*half, (0, 0, 0))]:
        raise ValueError('Reset changes outside the initial reset interval')
    if controls_seen['in_valid'] != [(0, (0, 0, 0)), (first-half, (1, 0, 0)),
                                    (events['last_input_ps']+half, (0, 0, 0))]:
        raise ValueError('Input valid changes outside the fixed streaming schedule')
    output_changes = [(t, value) for t, value in controls_seen['out_valid'] if t >= 6*half]
    if output_changes != [(events['first_output_check_ps']-1, (1, 0, 0)),
                          (last_check-1+period, (0, 0, 0))]:
        raise ValueError('Output valid changes outside the fill/drain schedule')
    expected_inputs = [(0, (0, 0, 0))]
    previous = 0
    for i, value in enumerate(inputs):
        if value != previous:
            expected_inputs.append((first-half+i*period, (value, 0, 0)))
        previous = value
    if controls_seen['x'] != expected_inputs:
        raise ValueError('Input data changes outside the falling-edge/held-input schedule')
    for i in range(n):
        at = sampled[first+i*period]
        if any(_known(at, name) != expected for name, expected in
               (('clk', 1), ('rst', 0), ('in_valid', 1),
                ('input_index', i), ('input_count', i+1))):
            raise ValueError('Input marker/valid schedule does not match ordered workload')
        for window in windows:
            sample = sampled[window['first_sample_ps']+i*period]
            signal = window['signal']
            value = _known(sample, signal)
            if _known(sample, 'rst') != 0:
                raise ValueError('Reset overlaps a measurement sample')
            if signal in ('x', 'l0') and value != inputs[i]:
                raise ValueError('Recorded input state disagrees with ordered reference')
            if signal in ('sc_flat', 'scores') and value != scores[i]:
                raise ValueError('Score availability does not match frame-aligned window')
            if signal in ('best', 'class_out') and value != classes[i]:
                raise ValueError('Class availability does not match frame-aligned window')
            if signal == 'scores' and any(_known(sample, name) != expected for name, expected in
                    (('out_valid', 1), ('output_index', i), ('output_count', i+1))):
                raise ValueError('Output marker/valid schedule does not match window')
    final_state = sampled[done]
    if any(_known(final_state, name) != expected for name, expected in
           (('in_valid', 0), ('out_valid', 0), ('capture_done', 1),
            ('input_count', n), ('output_count', n), ('x', inputs[-1]))):
        raise ValueError('Final drain/held-input state is inconsistent')
    for window in windows:
        declaration = selected[window['signal']]
        window.update(identifier=declaration['identifier'], width=declaration['width'],
                      known_samples_verified=n)
    return dict(n_images=n, architecture=params, clock=clock, windows=windows,
                window_policy='Per-observation (frame0 settled, frameN-1 settled]; '
                              'N states and N-1 adjacent pairs; exclude initialization',
                validated_boundaries=events,
                diagnostic_burst_envelope=dict(first_data_drive_ps=first-half,
                                                final_output_check_ps=last_check,
                                                note='Includes required fill/drain processing; '
                                                     'not an approved device-energy denominator'),
                checks=dict(rising_edges=len(rising), falling_edges=len(falling),
                            raw_trace_reset_and_tail_verified=True,
                            reset_and_valid_continuity_verified=True,
                            input_drive_and_hold_continuity_verified=True,
                            io_reference_and_marker_alignment_verified=True,
                            logical_layers_known_at_samples=True,
                            logical_layer_numpy_comparison=False))


def report_windows(capture):
    capture = Path(capture).resolve()
    output = Path(tempfile.mkdtemp(prefix='activity-windows.', dir=capture))
    destination = output/'result.json'
    result = dict(status='running', directory=str(output), scope=__doc__.strip())
    try:
        original = (capture/'result.json').read_bytes()
        manifest = json.loads(original)
        if manifest.get('status') != 'passed':
            raise ValueError('Expected a passed full-capture archive')
        hashes = manifest['files_sha256']
        required = {'dlgn.vcd', 'model.json', 'x_test_bits.npy', 'params.json',
                    'input_indices.json', 'events.csv', 'dlgn_top.sv', 'tb_activity_capture.sv',
                    'x.hex', 'exp_scores.hex', 'exp_class.hex'}
        if not required <= hashes.keys():
            raise ValueError('Missing required capture hashes')
        for name, expected in hashes.items():
            if Path(name).name != name or digest(capture/name) != expected:
                raise ValueError(f'Capture artifact changed or unsafe name: {name}')
        validated = validate_windows(capture, manifest)
        if original != (capture/'result.json').read_bytes() or any(
                digest(capture/name) != expected for name, expected in hashes.items()):
            raise ValueError('Capture changed during window validation')
        (output/'capture-manifest.json').write_bytes(original)
        sources = [Path(__file__).resolve(), ROOT/'dlgn/vcd_activity.py',
                   ROOT/'scripts/analyze_waveform.py', ROOT/'scripts/capture_baseline_waveform.py']
        for source in sources:
            shutil.copyfile(source, output/source.name)
        result.update(status='passed', capture_directory=str(capture),
                      capture_report_sha256=digest(capture/'result.json'),
                      capture_artifacts_sha256=hashes,
                      source_sha256={str(p): digest(p) for p in sources},
                      analysis_artifacts_sha256={p.name: digest(output/p.name) for p in sources},
                      **validated,
                      limits=['Staggered per-observation windows are not a global physical total',
                              'Recorded events inside windows may include simulator intermediates',
                              'Signal-category accounting remains 3.6; settled layer/Python comparison 3.7',
                              'No power/energy or novelty claim; historical inspected data remain exploratory'])
        result['analysis_artifacts_sha256']['capture-manifest.json'] = digest(output/'capture-manifest.json')
    except Exception as exc:
        result.update(status='failed', error=str(exc))
        raise
    finally:
        destination.write_text(json.dumps(result, indent=2)+'\n')
        print(f'Activity-window evidence: {destination}', flush=True)
    return result


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('capture', type=Path)
    args = ap.parse_args()
    report_windows(args.capture)
