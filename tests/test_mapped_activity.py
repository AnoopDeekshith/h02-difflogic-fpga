"""Independent mapped-bit coverage, scalar-reference and event-oracle checks.

The oracle decodes the canonical VCD bus directly as strings and identifies
netbits from raw Yosys ports, never from the production counter/parser.
"""
from bisect import bisect_right
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
from test_activity_windows import make_capture, refresh_hash, inject_value, trace_values
from test_activity_numpy import scalar_reference


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def raw_bit_oracle(path, signal='activity_nodes', start=None, end=None):
    """Direct string, little-endian per-bit event tally, no VCD library calls."""
    chosen = None
    width = None
    previous = None
    timestamp = 0
    header = True
    rows = None
    for line in Path(path).read_text().splitlines():
        words = line.split()
        if not words:
            continue
        if header:
            if words[0] == '$var' and words[4] == signal:
                assert chosen is None, 'Canonical vector declared more than once'
                width, chosen = int(words[2]), words[3]
                rows = [dict(known_bit_toggles=0, rises=0, falls=0,
                             unknown_bit_changes=0, four_state_bit_changes=0,
                             initial_unknown_bits=0) for _ in range(width)]
            elif words[0] == '$enddefinitions':
                header = False
            continue
        if words[0].startswith('#'):
            timestamp = int(words[0][1:])
            continue
        if words[0][0] in 'bB' and len(words) == 2:
            value, identifier = words[0][1:].lower(), words[1]
        elif words[0][0] in '01xXzZ':
            value, identifier = words[0][0].lower(), words[0][1:]
        else:
            continue
        if identifier != chosen:
            continue
        assert len(value) <= width
        value = value.rjust(width, value[0] if value[0] in 'xz' else '0')[::-1]
        included = (start is None or timestamp > start) and (end is None or timestamp <= end)
        if previous is None:
            if included:
                for row, bit in zip(rows,value):
                    row['initial_unknown_bits'] += bit in 'xz'
        elif included:
            for row,a,b in zip(rows,previous,value):
                if a != b:
                    row['four_state_bit_changes'] += 1
                    if a in '01' and b in '01':
                        row['known_bit_toggles'] += 1
                        row['rises' if b == '1' else 'falls'] += 1
                    else:
                        row['unknown_bit_changes'] += 1
        previous = value
    assert chosen is not None and previous is not None
    return rows


def raw_net_universe(design):
    top = design['modules']['dlgn_top']
    bits = set()
    constants = 0
    for port in top['ports'].values():
        for bit in port['bits']:
            if type(bit) is int:
                bits.add(bit)
            else:
                constants += 1
    for cell in top['cells'].values():
        for connection in cell['connections'].values():
            for bit in connection:
                if type(bit) is int:
                    bits.add(bit)
                else:
                    constants += 1
    return sorted(bits), constants


def tiny_design():
    """Two LUTs plus a FF, shared buses/aliases and explicit constant pins."""
    def cell(kind, connections, outputs):
        return dict(type=kind, parameters={}, attributes={}, connections=connections,
                    port_directions={name:'output' if name in outputs else 'input'
                                     for name in connections})
    return dict(modules=dict(dlgn_top=dict(attributes={},
        ports=dict(clk=dict(direction='input',bits=[2]), rst=dict(direction='input',bits=[3]),
                   in_valid=dict(direction='input',bits=[4]), x=dict(direction='input',bits=[5,6]),
                   scores=dict(direction='output',bits=[8,7,'0']),
                   class_out=dict(direction='output',bits=[9]),
                   out_valid=dict(direction='output',bits=[4])),
        cells=dict(a=cell('SB_LUT4',dict(I0=[5],I1=[6],I2=['0'],I3=['1'],O=[7]),['O']),
                   b=cell('SB_LUT4',dict(I0=[7],I1=[5],I2=['0'],I3=['0'],O=[8]),['O']),
                   q=cell('SB_DFF',dict(C=[2],D=[8],Q=[9]),['Q'])),
        netnames=dict(bus=dict(bits=[8,7,5,'0'],hide_name=0,attributes={}),
                      repeated=dict(bits=[7,7],hide_name=0,attributes={}),
                      alias=dict(bits=[5,6],hide_name=0,attributes={}),
                      stale_unused=dict(bits=[99],hide_name=1,attributes={})))) )


def assert_count_oracle(actual, expected):
    keymap = dict(known_toggles='known_bit_toggles', rises='rises', falls='falls',
                  unknown_changes='unknown_bit_changes', four_state_changes='four_state_bit_changes',
                  initial_unknown_bits='initial_unknown_bits')
    assert len(actual['per_bit']) == len(expected)
    for a,e in zip(actual['per_bit'],expected):
        for key,oracle_key in keymap.items():
            assert a[key] == e[oracle_key]
    for key,oracle_key in keymap.items():
        assert actual['totals'][key] == sum(e[oracle_key] for e in expected)


def test_numeric_net_identity_deduplicates_bus_aliases_and_excludes_constants():
    from mapped_activity import instrument_json
    design = tiny_design()
    preserved = deepcopy(design)
    instrumented, ledger = instrument_json(design)
    ids, constants = raw_net_universe(design)
    assert ids == list(range(2,10)) and constants == 5
    assert design == preserved
    assert [e['bit_id'] for e in ledger['entries']] == ids
    assert instrumented['modules']['dlgn_top']['netnames']['activity_nodes']['bits'] == ids
    assert instrumented['modules']['dlgn_top']['cells'] == design['modules']['dlgn_top']['cells']
    assert ledger['category_bits'] == dict(clock=1,control=2,data_input=2,lut=2,ff=1)
    assert 'stale_unused[0]' not in [a for e in ledger['entries'] for a in e['aliases']]
    seven = next(e for e in ledger['entries'] if e['bit_id']==7)
    assert set(seven['aliases']) == {'bus[1]','repeated[0]','repeated[1]'}


@pytest.mark.parametrize('fault',['multiple_driver','input_cell_conflict','undriven',
    'unsupported_primitive','wrong_output_direction','unknown_input_port','wrong_width',
    'inout','reserved_bus','nonbinary_constant','unknown_ff','missing_ff_pin',
    'wide_scalar_port','port_width_mismatch'])
def test_bad_net_coverage_or_driver_contract_rejected(fault):
    from mapped_activity import instrument_json
    design = tiny_design()
    top = design['modules']['dlgn_top']
    if fault == 'multiple_driver':
        top['cells']['duplicate'] = deepcopy(top['cells']['a'])
    elif fault == 'input_cell_conflict':
        top['cells']['a']['connections']['O'] = [5]
    elif fault == 'undriven':
        top['cells']['a']['connections']['I0'] = [123]
    elif fault == 'unsupported_primitive':
        top['cells']['a']['type'] = 'SB_UNKNOWN'
    elif fault == 'wrong_output_direction':
        top['cells']['a']['port_directions']['O'] = 'input'
    elif fault == 'unknown_input_port':
        top['cells']['a']['connections']['UNKNOWN'] = [5]
        top['cells']['a']['port_directions']['UNKNOWN'] = 'input'
    elif fault == 'wrong_width':
        top['cells']['a']['connections']['I0'] = [5,6]
    elif fault == 'unknown_ff':
        top['cells']['q']['type'] = 'SB_DFF_MADE_UP'
    elif fault == 'missing_ff_pin':
        top['cells']['q']['type'] = 'SB_DFFR'
    elif fault == 'inout':
        top['ports']['x']['direction'] = 'inout'
    elif fault == 'reserved_bus':
        top['netnames']['activity_nodes'] = dict(bits=[7])
    elif fault == 'nonbinary_constant':
        top['cells']['a']['connections']['I0'] = ['2']
    elif fault == 'wide_scalar_port':
        top['ports']['clk']['bits'] = [2, 3]
    widths = None
    if fault == 'port_width_mismatch':
        widths = dict(clk=1, rst=1, in_valid=1, out_valid=1, x=3, class_out=1, scores=3)
    with pytest.raises(ValueError):
        instrument_json(design, widths)


def test_declared_port_widths_accepted():
    from mapped_activity import instrument_json
    instrument_json(tiny_design(), dict(clk=1, rst=1, in_valid=1, out_valid=1,
                                        x=2, class_out=1, scores=3))


@pytest.mark.parametrize('start,end',[(None,None),(0,12),(5,10),(10,None)])
def test_canonical_bus_counts_known_unknown_and_same_timestamp_events(tmp_path,start,end):
    from mapped_activity import instrument_json,count_activity
    _,ledger = instrument_json(tiny_design())
    path = tmp_path/'synthetic.vcd'
    path.write_text('''$timescale 1ps $end
$scope module tb_mapped $end
$scope module dut $end
$var wire 8 ! activity_nodes [7:0] $end
$var wire 2 " duplicate_alias [1:0] $end
$upscope $end
$upscope $end
$enddefinitions $end
#0
$dumpvars
bx !
b0 "
$end
#1
b0 !
#5
b110001 !
b100001 !
b100001 !
#10
b1x100001 !
#11
bz !
#12
b11110000 !
#15
b0 !
''')
    result = count_activity(path,ledger,start,end)
    assert_count_oracle(result,raw_bit_oracle(path,start=start,end=end))
    assert result['observed_net_bits'] == 8
    if start is None and end is None:
        assert result['max_bus_records_per_tick'] == 3  # synthetic #5 has three records
    assert sum(c['known_toggles'] for c in result['categories'].values()) == result['totals']['known_toggles']


@pytest.mark.parametrize('start', [15, 10**12])
def test_window_starting_at_or_after_trace_end_rejected(tmp_path, start):
    from mapped_activity import instrument_json, count_activity
    _, ledger = instrument_json(tiny_design())
    path = tmp_path/'short.vcd'
    path.write_text('$timescale 1ps $end\n$scope module tb $end\n$scope module dut $end\n'
                    '$var wire 8 ! activity_nodes [7:0] $end\n$upscope $end\n$upscope $end\n'
                    '$enddefinitions $end\n#0\nb0 !\n#15\nb1 !\n')
    with pytest.raises(ValueError):
        count_activity(path, ledger, start_tick=start)


@pytest.fixture(scope='module')
def toy_mapped(tmp_path_factory):
    from capture_mapped_activity import capture
    folder = tmp_path_factory.mktemp('mapped-real-tools')
    baseline = folder/'baseline'
    make_capture(baseline)
    before = (baseline/'result.json').read_bytes()
    result = capture(baseline)
    assert (baseline/'result.json').read_bytes() == before
    return Path(result['directory'])


def audit_mapped_result(folder):
    """Independent full result audit, also reusable for 450-vector archives."""
    folder = Path(folder)
    result = json.loads((folder/'result.json').read_text())
    assert result['status'] == 'passed'
    mapped = json.loads((folder/'mapped.json').read_text())
    instrumented = json.loads((folder/'instrumented.json').read_text())
    ledger = json.loads((folder/'net-ledger.json').read_text())
    ids, constants = raw_net_universe(mapped)
    assert constants > 0
    assert [e['bit_id'] for e in ledger['entries']] == ids
    assert instrumented['modules']['dlgn_top']['netnames']['activity_nodes']['bits'] == ids
    assert instrumented['modules']['dlgn_top']['cells'] == mapped['modules']['dlgn_top']['cells']
    refs,ties = scalar_reference(folder)
    decls,snapshots = trace_values(folder/'mapped.vcd')
    times = sorted(snapshots)
    events = result['simulation']['event_ledger']
    period = 83334
    for i in range(len(refs['scores'])):
        input_time = events['first_input_ps']+i*period
        output_time = events['first_output_check_ps']+i*period
        inp = snapshots[times[bisect_right(times,input_time)-1]]
        out = snapshots[times[bisect_right(times,output_time)-1]]
        assert inp['tb_capture.dut.x'] == refs['x'][i]
        assert out['tb_capture.dut.scores'] == refs['scores'][i]
        assert out['tb_capture.dut.class_out'] == refs['class_out'][i]
        assert out['tb_capture.dut.out_valid'] == 1
    for name,activity in result['activity'].items():
        if not isinstance(activity,dict):
            continue
        window=activity['window']
        oracle = raw_bit_oracle(folder/'mapped.vcd',start=window['start_exclusive_tick'],
                                end=window['end_inclusive_tick'])
        assert_count_oracle(activity,oracle)
        assert activity['observed_net_bits'] == len(ids)
        grouped={}
        for entry,counts in zip(ledger['entries'],oracle):
            g=grouped.setdefault(entry['category'],dict(known_toggles=0,rises=0,falls=0,unknown_changes=0))
            for a,b in [('known_toggles','known_bit_toggles'),('rises','rises'),('falls','falls'),
                        ('unknown_changes','unknown_bit_changes')]:
                g[a] += counts[b]
        for category,counts in grouped.items():
            for key,value in counts.items():
                assert activity['categories'][category][key] == value
    burst = result['activity']['complete_burst']['window']
    assert burst == dict(start_exclusive_tick=events['first_input_ps']-41667-1,
                         end_inclusive_tick=events['last_output_check_ps'])
    commands=json.loads((folder/'commands.json').read_text())
    assert '-device u' in commands[0][-1]
    compile_command = next(c for c in commands if any('iverilog' in str(v) for v in c))
    assert not any('specify' in v or v.startswith('-D') for v in compile_command)
    assert 'synth_ice40 -device u -top dlgn_top' in (folder/'synth.log').read_text()
    for name,expected in result['files_sha256'].items():
        assert sha(folder/name) == expected
    for name,expected in result['source_sha256'].items():
        assert sha(name) == expected
    baseline = Path(result['baseline_capture'])
    assert sha(baseline/'result.json') == result['baseline_manifest_sha256']
    for name,expected in result['baseline_artifacts_sha256'].items():
        assert sha(baseline/name) == expected
    return dict(images=len(refs['scores']),tied_score_images=ties,unique_mapped_bits=len(ids),
                scalar_scores_classes=True,independent_per_bit_event_oracle=True,
                independent_top_cell_port_union=True,constant_pin_occurrences=constants,
                hashed_capture_files=len(result['files_sha256']),
                source_hashes=len(result['source_sha256']))


def test_real_synthesis_and_simulation_match_scalar_and_bit_oracles(toy_mapped):
    audit = audit_mapped_result(toy_mapped)
    assert audit['images'] == 16


def test_reanalysis_preserves_original_archive(toy_mapped):
    from capture_mapped_activity import analyze
    original = (toy_mapped/'result.json').read_bytes()
    hashes = json.loads(original)['files_sha256']
    result = analyze(toy_mapped)
    assert result['status'] == 'passed'
    assert (toy_mapped/'result.json').read_bytes() == original
    assert all(sha(toy_mapped/name)==value for name,value in hashes.items())
    assert (Path(result['directory'])/'capture-manifest.json').read_bytes() == original


def mapped_inject(folder,signal,timestamp,bits):
    path=Path(folder)/'mapped.vcd'
    decls,_=trace_values(path)
    identifier,width=decls[signal]
    value=f'b{bits} {identifier}' if width>1 else bits+identifier
    lines=path.read_text().splitlines()
    pos=next((i for i,line in enumerate(lines) if line.startswith('#') and int(line[1:])>timestamp),len(lines))
    # Insert before next later timestamp, retaining original event order.
    if f'#{timestamp}' not in lines:
        lines[pos:pos]=[f'#{timestamp}',value]
    else:
        lines.insert(pos,value)
    path.write_text('\n'.join(lines)+'\n')
    refresh_hash(folder,'mapped.vcd')


@pytest.mark.parametrize('fault',['hash','missing_hash','scores','class','input_order','numpy_nonbinary',
    'rtl','ledger','input_pulse','valid_pulse','reset_pulse','output_marker','clock','unknown_input',
    'canonical_port_disagreement'])
def test_rebound_hash_semantic_faults_rejected(toy_mapped,tmp_path,fault):
    from capture_mapped_activity import analyze
    folder=tmp_path/'capture'
    shutil.copytree(toy_mapped,folder,ignore=shutil.ignore_patterns('mapped-analysis.*'))
    manifest=json.loads((folder/'result.json').read_text())
    first=manifest['simulation']['event_ledger']['first_input_ps']
    if fault=='hash':
        with (folder/'mapped.vcd').open('a') as f:
            f.write('$comment modified $end\n')
    elif fault=='missing_hash':
        del manifest['files_sha256']['mapped.vcd']
        (folder/'result.json').write_text(json.dumps(manifest))
    elif fault in ('scores','class'):
        name='exp_scores.hex' if fault=='scores' else 'exp_class.hex'
        lines=(folder/name).read_text().splitlines()
        lines[0]=format(int(lines[0],16)^1,'x')
        (folder/name).write_text('\n'.join(lines)+'\n')
        refresh_hash(folder,name)
    elif fault=='input_order':
        (folder/'input_indices.json').write_text(json.dumps(list(reversed(range(16)))))
        refresh_hash(folder,'input_indices.json')
    elif fault=='numpy_nonbinary':
        values=np.load(folder/'x_test_bits.npy').astype(np.uint8)
        values[0,0]=2
        np.save(folder/'x_test_bits.npy',values)
        refresh_hash(folder,'x_test_bits.npy')
    elif fault=='rtl':
        with (folder/'dlgn_top.sv').open('a') as f:
            f.write('// rebound source mutation\n')
        refresh_hash(folder,'dlgn_top.sv')
    elif fault=='ledger':
        p=folder/'net-ledger.json'
        data=json.loads(p.read_text())
        data['entries'][0]['bit_id']+=10000
        p.write_text(json.dumps(data))
        refresh_hash(folder,p.name)
    elif fault=='output_marker':
        t=manifest['simulation']['event_ledger']['first_output_check_ps']
        mapped_inject(folder,'tb_capture.output_index',t,'111')
    elif fault=='clock':
        mapped_inject(folder,'tb_capture.dut.clk',first+100,'0')
        mapped_inject(folder,'tb_capture.dut.clk',first+101,'1')
    elif fault=='canonical_port_disagreement':
        # Perturb canonical clock bit but keep standalone port untouched.
        ledger=json.loads((folder/'net-ledger.json').read_text())
        clockbit=json.loads((folder/'mapped.json').read_text())['modules']['dlgn_top']['ports']['clk']['bits'][0]
        j=next(i for i,e in enumerate(ledger['entries']) if e['bit_id']==clockbit)
        _,states=trace_values(folder/'mapped.vcd')
        state=states[max(t for t in states if t<=first+100)]['tb_capture.dut.activity_nodes']
        mapped_inject(folder,'tb_capture.dut.activity_nodes',first+100,format(state^(1<<j),'b'))
        # Rebind counts too: consistency validation must detect contradictory aliases.
        from mapped_activity import count_activity
        manifest=json.loads((folder/'result.json').read_text())
        for name in ('whole_trace','complete_burst'):
            w=manifest['activity'][name]['window']
            manifest['activity'][name]=count_activity(folder/'mapped.vcd',ledger,w['start_exclusive_tick'],w['end_inclusive_tick'])
        (folder/'result.json').write_text(json.dumps(manifest))
    else:
        name={'input_pulse':'x','valid_pulse':'in_valid','reset_pulse':'rst','unknown_input':'x'}[fault]
        value={'input_pulse':'1','valid_pulse':'0','reset_pulse':'1','unknown_input':'x'}[fault]
        mapped_inject(folder,'tb_capture.dut.'+name,first+100,value)
    with pytest.raises(ValueError):
        analyze(folder)
    attempts=list(folder.glob('mapped-analysis.*/result.json'))
    assert len(attempts)==1
    assert json.loads(attempts[0].read_text())['status']=='failed'


@pytest.mark.parametrize('fault',['missing_original_hash','rtl','nonbinary','reference','row_order','clock'])
def test_invalid_baseline_cannot_start_successful_mapping(tmp_path,fault):
    from capture_mapped_activity import capture
    baseline=tmp_path/'baseline'
    make_capture(baseline)
    manifest=json.loads((baseline/'result.json').read_text())
    if fault=='missing_original_hash':
        del manifest['files_sha256']['simv']
        (baseline/'result.json').write_text(json.dumps(manifest))
    elif fault=='rtl':
        with (baseline/'dlgn_top.sv').open('a') as f:
            f.write('// cannot regenerate this exact file\n')
        refresh_hash(baseline,'dlgn_top.sv')
    elif fault=='nonbinary':
        x=np.load(baseline/'x_test_bits.npy').astype(np.uint8)
        x[0,0]=2
        np.save(baseline/'x_test_bits.npy',x)
        refresh_hash(baseline,'x_test_bits.npy')
    elif fault=='reference':
        p=baseline/'exp_scores.hex'
        lines=p.read_text().splitlines()
        lines[0]=format(int(lines[0],16)^1,'x')
        p.write_text('\n'.join(lines)+'\n')
        refresh_hash(baseline,p.name)
    elif fault=='row_order':
        (baseline/'input_indices.json').write_text(json.dumps(list(reversed(range(16)))))
        refresh_hash(baseline,'input_indices.json')
    else:
        manifest['clock']['simulated_period_ps']=83333
        (baseline/'result.json').write_text(json.dumps(manifest))
    before=(baseline/'result.json').read_bytes()
    with pytest.raises(ValueError):
        capture(baseline)
    assert (baseline/'result.json').read_bytes()==before
    reports=list(tmp_path.glob('mapped-activity.*/result.json'))
    assert len(reports)==1 and json.loads(reports[0].read_text())['status']=='failed'
