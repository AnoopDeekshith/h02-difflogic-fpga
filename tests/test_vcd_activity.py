"""Independent checks of digital VCD transition accounting, not energy.

The string-based oracle is deliberately separate from the production parser.
"""
from pathlib import Path
import hashlib
import json
import re
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dlgn.vcd_activity import analyze_vcd, VCDFormatError  # noqa: E402
from scripts import analyze_waveform  # noqa: E402


def string_oracle(path, start=None, end=None):
    """Count per-bit four-state changes directly from streamed VCD records."""
    declarations, previous, result = {}, {}, {}
    header = True
    time = 0
    for line in Path(path).read_text().splitlines():
        words = line.split()
        if not words:
            continue
        if header:
            if words[0] == '$var':
                width, identifier = int(words[2]), words[3]
                if identifier in declarations:
                    assert declarations[identifier] == width
                declarations[identifier] = width
                result.setdefault(identifier, dict(known=0, rises=0, falls=0,
                                                  unknown_changes=0, state_changes=0))
            elif words[0] == '$enddefinitions':
                header = False
            continue
        token = words[0]
        if token.startswith('#'):
            time = int(token[1:])
            continue
        if token.startswith('$'):
            continue
        if token[0] in 'bB':
            bits, identifier = token[1:].lower(), words[1]
        elif token[0] in '01xXzZ':
            bits, identifier = token[0].lower(), token[1:]
        else:
            raise AssertionError(f'Unexpected value record {line!r}')
        width = declarations[identifier]
        extension = bits[0] if bits[0] in 'xz' else '0'
        current = extension * (width - len(bits)) + bits
        old = previous.get(identifier)
        included = (start is None or time > start) and (end is None or time <= end)
        if old is not None and included:
            for before, after in zip(old, current):
                if before != after:
                    result[identifier]['state_changes'] += 1
                    if before in '01' and after in '01':
                        result[identifier]['known'] += 1
                        result[identifier]['rises' if after == '1' else 'falls'] += 1
                    else:
                        result[identifier]['unknown_changes'] += 1
        previous[identifier] = current
    assert not header
    return result


def write_trace(tmp_path, body, declarations=None, timescale='1ps'):
    if declarations is None:
        declarations = '$var wire 4 ! bus [3:0] $end\n$var wire 4 ! alias [3:0] $end\n$var wire 1 " flag $end'
    path = tmp_path / 'trace.vcd'
    path.write_text(f'''$timescale {timescale} $end
$scope module top $end
{declarations}
$upscope $end
$enddefinitions $end
{body}
''')
    return path


MIXED_BODY = '''#0
$dumpvars
b0 !
0"
$end
#5
b0011 !
1"
#5
b0001 !
b0001 !
#10
b1x01 !
0"
#15
bz !
#20
b0 !
#25
b1111 !
#30
b1111 !'''


def assert_oracle_matches(path, result, start=None, end=None):
    expected = string_oracle(path, start, end)
    assert {row['identifier'] for row in result['signals']} == set(expected)
    mapping = {'known': 'known_bit_toggles', 'rises': 'rises', 'falls': 'falls',
               'unknown_changes': 'unknown_bit_changes', 'state_changes': 'four_state_bit_changes'}
    for row in result['signals']:
        for independent_name, production_name in mapping.items():
            assert row['counts'][production_name] == expected[row['identifier']][independent_name]
    for independent_name, production_name in mapping.items():
        assert result['totals'][production_name] == sum(v[independent_name] for v in expected.values())


def test_hand_counted_four_state_bits_aliases_redundancy_and_same_timestamp(tmp_path):
    path = write_trace(tmp_path, MIXED_BODY)
    result = analyze_vcd(path)
    assert result['declaration_count'] == 3
    assert result['unique_identifier_count'] == 2
    assert result['first_timestamp_tick'] == 0
    assert result['last_timestamp_tick'] == 30
    total = result['totals']
    assert total['known_bit_toggles'] == 10
    assert total['rises'] == 8 and total['falls'] == 2
    assert total['unknown_bit_changes'] == 9
    assert total['four_state_bit_changes'] == 19
    assert total['observed_records'] == 12
    assert total['initializations'] == 2
    assert total['initial_unknown_bits'] == 0
    assert total['value_change_records'] == 8
    assert total['redundant_value_records'] == 2
    bus = next(row for row in result['signals'] if row['identifier'] == '!')
    assert {a['path'] for a in bus['aliases']} == {'top.bus[3:0]', 'top.alias[3:0]'}
    assert bus['counts']['known_bit_toggles'] == 8
    assert_oracle_matches(path, result)


@pytest.mark.parametrize('start,end', [(5, 20), (0, 30), (None, 5), (10, None)])
def test_windows_carry_preceding_state_and_use_open_left_closed_right(tmp_path, start, end):
    path = write_trace(tmp_path, MIXED_BODY)
    result = analyze_vcd(path, start_tick=start, end_tick=end)
    assert_oracle_matches(path, result, start, end)
    if start is not None:
        assert result['totals']['initializations'] == 0
    if start == 5 and end == 20:
        assert result['totals']['known_bit_toggles'] == 2
        assert result['totals']['unknown_bit_changes'] == 9


def test_unknown_initialization_is_observation_and_unknown_extension_is_preserved(tmp_path):
    path = write_trace(tmp_path, '#0\nbX !\n0"\n#1\nb1 !\n#2\nb0010 !\n#3\nbZ !')
    result = analyze_vcd(path)
    assert result['totals']['initializations'] == 2
    assert result['totals']['initial_unknown_bits'] == 4
    assert result['totals']['known_bit_toggles'] == 2
    assert result['totals']['rises'] == result['totals']['falls'] == 1
    assert result['totals']['unknown_bit_changes'] == 8
    assert_oracle_matches(path, result)


def test_ten_ns_multiline_header_and_multiple_records_per_line(tmp_path):
    path = tmp_path / 'multi.vcd'
    path.write_text('''$date test $end
$timescale
10 ns
$end
$scope module top $end
$var wire
1 ! flag
$end
$upscope $end
$enddefinitions $end
#0 $dumpvars 0! $end
#1 1! 0! #2 1!
''')
    result = analyze_vcd(path)
    assert result['timescale']['magnitude'] == 10
    assert result['timescale']['unit'] == 'ns'
    assert float(result['timescale']['seconds_per_tick']) == pytest.approx(1e-8)
    assert result['totals']['known_bit_toggles'] == 3
    assert result['totals']['rises'] == 2
    assert result['totals']['falls'] == 1


@pytest.mark.parametrize('start,end', [(-1, None), (None, -1), (5, 5), (6, 5),
                                       (None, 31), (31, None)])
def test_invalid_or_outside_trace_windows_are_rejected(tmp_path, start, end):
    path = write_trace(tmp_path, MIXED_BODY)
    with pytest.raises(ValueError):
        analyze_vcd(path, start_tick=start, end_tick=end)


@pytest.mark.parametrize('old,new', [
    ('$enddefinitions $end', ''),
    ('$timescale 1ps $end', ''),
    ('$var wire 4 ! alias', '$var wire 3 ! alias'),
    ('b0011 !', 'b10000 !'),
    ('b0011 !', 'b10q1 !'),
    ('b0011 !', 'b0011 ?'),
    ('#10', '#4'),
    ('$var wire 1 " flag', '$var real 1 " flag'),
    ('#15\nbz !', '#15\n$dumpoff\nbz !\n$end'),
    ('$dumpvars\nb0 !\n0"\n$end', '$dumpvars\nb0 !\n0"'),
])
def test_format_and_unsupported_dump_faults_are_rejected(tmp_path, old, new):
    path = write_trace(tmp_path, MIXED_BODY)
    path.write_text(path.read_text().replace(old, new))
    with pytest.raises(VCDFormatError):
        analyze_vcd(path)


def test_distinct_identifiers_with_equal_values_remain_separate_recorded_signals(tmp_path):
    declarations = '$var wire 1 ! a $end\n$var wire 1 " b $end'
    path = write_trace(tmp_path, '#0\n0!\n0"\n#1\n1!\n1"', declarations)
    result = analyze_vcd(path)
    assert result['unique_identifier_count'] == 2
    assert result['totals']['known_bit_toggles'] == 2


def test_unknown_gap_does_not_create_a_known_toggle(tmp_path):
    path = write_trace(tmp_path, '#0\n0!\n#1\nx!\n#2\n1!',
                       '$var wire 1 ! a $end')
    result = analyze_vcd(path)
    assert result['totals']['known_bit_toggles'] == 0
    assert result['totals']['unknown_bit_changes'] == 2


def test_dumpall_is_snapshot_and_repeated_unknown_values_are_not_changes(tmp_path):
    path = write_trace(tmp_path, '#0\n$dumpvars\nx!\n$end\n#1\n$dumpall\nx!\n$end\n#2\nz!',
                       '$var wire 1 ! a $end')
    result = analyze_vcd(path)
    assert result['totals']['initial_unknown_bits'] == 1
    assert result['totals']['unknown_value_records'] == 3
    assert result['totals']['redundant_value_records'] == 1
    assert result['totals']['unknown_bit_changes'] == 1
    assert result['totals']['known_bit_toggles'] == 0


def test_malformed_content_after_end_window_still_rejects_whole_trace(tmp_path):
    path = write_trace(tmp_path, MIXED_BODY + '\n#40\nr1.25 !')
    with pytest.raises(VCDFormatError):
        analyze_vcd(path, end_tick=5)


def test_scalar_record_cannot_initialize_a_vector(tmp_path):
    path = write_trace(tmp_path, '#0\n0!')
    with pytest.raises(VCDFormatError):
        analyze_vcd(path)


def test_duplicate_hierarchical_declaration_path_is_rejected(tmp_path):
    path = write_trace(tmp_path, '#0\n0!',
                       '$var wire 1 ! a $end\n$var wire 1 " a $end')
    with pytest.raises(VCDFormatError):
        analyze_vcd(path)


def _capture_fixture(tmp_path):
    """Minimal hash-bound archive fixture; not a real completed FPGA capture."""
    trace = write_trace(tmp_path, MIXED_BODY)
    trace.rename(tmp_path / 'dlgn.vcd')
    for name in ('model.json', 'x_test_bits.npy', 'params.json', 'input_indices.json',
                 'events.csv', 'dlgn_top.sv', 'tb_activity_capture.sv'):
        (tmp_path / name).write_text('Synthetic archived artifact for hash testing\n')
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.iterdir()}
    (tmp_path / 'result.json').write_text(json.dumps(dict(status='passed', files_sha256=hashes)))
    return hashes


def test_analysis_wrapper_binds_and_preserves_capture_files(tmp_path):
    hashes = _capture_fixture(tmp_path)
    manifest_before = (tmp_path / 'result.json').read_bytes()
    result = analyze_waveform.analyze_capture(tmp_path)
    assert result['status'] == 'passed'
    assert result['analysis']['totals']['known_bit_toggles'] == 10
    assert result['capture_artifacts_sha256'] == hashes
    assert (tmp_path / 'result.json').read_bytes() == manifest_before
    for name, expected in hashes.items():
        assert hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() == expected
    output = Path(result['directory'])
    assert (output / 'capture-manifest.json').read_bytes() == manifest_before
    for name, expected in result['analysis_artifacts_sha256'].items():
        assert hashlib.sha256((output / name).read_bytes()).hexdigest() == expected


@pytest.mark.parametrize('fault', ['trace_hash', 'unsafe_name', 'failed_status', 'missing_hash'])
def test_analysis_wrapper_retains_failed_attempt_and_rejects_unbound_capture(tmp_path, fault):
    _capture_fixture(tmp_path)
    path = tmp_path / 'result.json'
    manifest = json.loads(path.read_text())
    if fault == 'trace_hash':
        with (tmp_path / 'dlgn.vcd').open('a') as dest:
            dest.write('#40\n')
    elif fault == 'unsafe_name':
        manifest['files_sha256']['../outside'] = '0' * 64
    elif fault == 'failed_status':
        manifest['status'] = 'failed'
    elif fault == 'missing_hash':
        del manifest['files_sha256']['events.csv']
    if fault != 'trace_hash':
        path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        analyze_waveform.analyze_capture(tmp_path)
    attempts = list(tmp_path.glob('activity-analysis.*/result.json'))
    assert len(attempts) == 1
    assert json.loads(attempts[0].read_text())['status'] == 'failed'


def test_analysis_wrapper_rejects_manifest_change_during_analysis(tmp_path, monkeypatch):
    _capture_fixture(tmp_path)
    parser = analyze_waveform.analyze_vcd
    def mutate_manifest(path, start, end):
        result = parser(path, start, end)
        (tmp_path / 'result.json').write_text('{}')
        return result
    monkeypatch.setattr(analyze_waveform, 'analyze_vcd', mutate_manifest)
    with pytest.raises(ValueError, match='changed during analysis'):
        analyze_waveform.analyze_capture(tmp_path)
