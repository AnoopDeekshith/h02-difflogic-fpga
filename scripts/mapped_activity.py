"""Unique iCE40 mapped-net-bit instrumentation and zero-delay VCD event counting.

Numeric Yosys bit IDs define identity. Netname aliases and VCD identifiers do not.
"""
from collections import Counter, defaultdict
from pathlib import Path
import re

from dlgn.vcd_activity import _Tokens, _header, _state, analyze_vcd

PORTS = {'clk': 'input', 'rst': 'input', 'in_valid': 'input', 'x': 'input',
         'out_valid': 'output', 'class_out': 'output', 'scores': 'output'}
CELL_PINS = {
    'SB_LUT4': {'I0': 'input', 'I1': 'input', 'I2': 'input', 'I3': 'input', 'O': 'output'},
    'SB_CARRY': {'I0': 'input', 'I1': 'input', 'CI': 'input', 'CO': 'output'},
}


def _bit(bit):
    if type(bit) is int and bit >= 0:
        return bit
    if type(bit) is str and bit.lower() in ('0', '1', 'x', 'z'):
        return None
    raise ValueError(f'Invalid Yosys bit representation: {bit!r}')


SCALAR_PORTS = ('clk', 'rst', 'in_valid', 'out_valid')
PRIMARY_CATEGORY = {'clk': 'clock', 'rst': 'control', 'in_valid': 'control', 'x': 'data_input'}


def port_widths(params):
    """Expected standalone-core port widths from exporter parameters."""
    return dict(clk=1, rst=1, in_valid=1, out_valid=1, x=params['IN'],
                class_out=params['CW'], scores=params['K']*params['SW'])


def instrument_json(design, widths=None):
    """Add a canonical observation bus without changing primitive connections.

    Return a modified JSON design and a ledger of every observed numeric bit.
    Reject any nonconstant bit without exactly one recognized driver. Scalar
    ports must be one bit; `widths` (see port_widths) checks every port.
    """
    import copy
    design = copy.deepcopy(design)
    modules = design.get('modules', {})
    if 'dlgn_top' not in modules or any(
            name != 'dlgn_top' and 'blackbox' not in module.get('attributes', {})
            for name, module in modules.items()):
        raise ValueError('Expected flattened dlgn_top plus only unused blackbox definitions')
    top = modules['dlgn_top']
    cells, ports = top['cells'], top['ports']
    drivers = defaultdict(list)
    users = defaultdict(list)
    aliases = defaultdict(list)
    if set(ports) != set(PORTS):
        raise ValueError('Unexpected standalone core top ports')
    for name, port in ports.items():
        if port['direction'] != PORTS[name]:
            raise ValueError(f'Incorrect top port direction: {name}')
        expected = (widths or {}).get(name, 1 if name in SCALAR_PORTS else None)
        if expected is not None and len(port['bits']) != expected:
            raise ValueError(f'Incorrect top port width: {name}')
        for offset, bit in enumerate(port['bits']):
            if _bit(bit) is None:
                continue
            users[bit].append(f'port:{name}[{offset}]')
            if port['direction'] == 'input':
                drivers[bit].append(f'primary:{name}[{offset}]')
    counts = Counter()
    for name, cell in cells.items():
        kind = cell['type']
        ff = re.fullmatch(r'SB_DFF(N?)(E?)(SR|R|SS|S)?', kind)
        if kind not in ('SB_LUT4', 'SB_CARRY') and ff is None:
            raise ValueError(f'Unclassified primitive {kind}')
        counts[kind] += 1
        if ff:
            pins = {'C':'input', 'D':'input', 'Q':'output'}
            if ff.group(2):
                pins['E'] = 'input'
            if ff.group(3) in ('R','SR'):
                pins['R'] = 'input'
            if ff.group(3) in ('S','SS'):
                pins['S'] = 'input'
        else:
            pins = CELL_PINS[kind]
        if set(cell['connections']) != set(pins):
            raise ValueError(f'Missing or unknown {kind} pin on {name}')
        if set(cell['connections']) != set(cell['port_directions']):
            raise ValueError(f'Missing cell port direction on {name}')
        allowed = {'SB_LUT4': {'O'}, 'SB_CARRY': {'CO'}}.get(kind, {'Q'})
        for port, bits in cell['connections'].items():
            direction = cell['port_directions'][port]
            if port not in pins or direction != pins[port] or len(bits) != 1:
                raise ValueError(f'Incorrect {kind}.{port} pin shape/direction')
            if direction == 'output' and port not in allowed:
                raise ValueError(f'Unclassified driver {kind}.{port}')
            for bit in bits:
                if _bit(bit) is None:
                    continue
                users[bit].append(f'{name}:{kind}.{port}')
                if direction == 'output':
                    drivers[bit].append(f'{name}:{kind}.{port}')
    for name, net in top.get('netnames', {}).items():
        for offset, bit in enumerate(net['bits']):
            if _bit(bit) is not None:
                aliases[bit].append(f'{name}[{offset}]')
    bits = sorted(users)
    if not bits:
        raise ValueError('No mapped nets to observe')
    entries = []
    for bit in bits:
        if len(drivers[bit]) != 1:
            raise ValueError(f'Net bit {bit} has {len(drivers[bit])} drivers: {drivers[bit]}')
        driver = drivers[bit][0]
        category = (PRIMARY_CATEGORY[driver[8:].split('[')[0]] if driver.startswith('primary:') else
                    'lut' if driver.endswith(':SB_LUT4.O') else
                    'carry' if driver.endswith(':SB_CARRY.CO') else 'ff')
        entries.append(dict(bit_id=bit, driver=driver, category=category,
                            aliases=sorted(set(aliases[bit])), users=sorted(set(users[bit]))))
    if 'activity_nodes' in top.get('netnames', {}) or 'activity_nodes' in ports:
        raise ValueError('Reserved activity bus already exists')
    top.setdefault('netnames', {})['activity_nodes'] = {
        'hide_name': 0, 'bits': bits, 'attributes': {'keep': '1'}}
    return design, dict(schema=1, module='dlgn_top', bus='activity_nodes',
                        bit_order='bus bit index equals entry index; JSON bits sorted ascending',
                        entries=entries, primitive_counts=dict(sorted(counts.items())),
                        category_bits=dict(sorted(Counter(e['category'] for e in entries).items())),
                        excluded_constants=True, numeric_bit_dedup=True)


def count_activity(vcd, ledger, start_tick=None, end_tick=None):
    """Count bus-bit changes between successive recorded VCD values.

    Same-tick records would be counted, but Icarus writes each identifier at
    most once per timestamp (its final value), so zero-delay intermediate
    pulses never reach the file. `max_bus_records_per_tick` reports this; a
    value of 1 means the counts are settled per-timestamp changes.
    The first value of each bit initializes it. X/Z touching changes are
    separate from known 0/1 toggles. Window is (start_tick, end_tick].
    """
    if start_tick is not None and (type(start_tick) is not int or start_tick < 0):
        raise ValueError('Invalid start tick')
    if end_tick is not None and (type(end_tick) is not int or end_tick < 0):
        raise ValueError('Invalid end tick')
    if start_tick is not None and end_tick is not None and start_tick >= end_tick:
        raise ValueError('Invalid window')
    # Validate the whole file, including nonbus declarations and records.
    validated = analyze_vcd(vcd)
    entries = ledger['entries']
    width = len(entries)
    with Path(vcd).open() as source:
        tokens = _Tokens(source)
        signals, scale, _ = _header(tokens)
        matched = [(ident, signal) for ident, signal in signals.items() if any(
            alias['reference'] == ledger['bus'] and alias['scope'][-1:] == ['dut']
            for alias in signal['aliases'])]
        if len(matched) != 1 or matched[0][1]['width'] != width:
            raise ValueError('Missing or incorrectly sized canonical mapped bus')
        bus_id = matched[0][0]
        per_bit = [dict(known_toggles=0, rises=0, falls=0, unknown_changes=0,
                        four_state_changes=0, initial_unknown_bits=0) for _ in entries]
        state = None
        tick = 0
        first_tick = None
        dump = False
        bus_records = 0
        records_this_tick = 0
        max_per_tick = 0
        for token in iter(tokens.get, None):
            if token == '$comment':
                tokens.block()
            elif token in ('$dumpvars', '$dumpall'):
                if dump:
                    tokens.fail('Nested VCD dump')
                dump = True
            elif token == '$end':
                if not dump:
                    tokens.fail('Unexpected VCD $end')
                dump = False
            elif token.startswith('#'):
                if dump or not token[1:].isdecimal() or int(token[1:]) < tick:
                    tokens.fail('Invalid VCD timestamp')
                if int(token[1:]) != tick:
                    records_this_tick = 0
                tick = int(token[1:])
                if first_tick is None:
                    first_tick = tick
            elif token.startswith('$'):
                tokens.fail(f'Unsupported VCD directive {token}')
            elif token[0] in 'bB':
                bits, ident = token[1:], tokens.need()
                if ident not in signals:
                    tokens.fail(f'Undeclared VCD identifier {ident}')
                if ident != bus_id:
                    continue
                new = _state(bits, width, tokens)
                bus_records += 1
                records_this_tick += 1
                max_per_tick = max(max_per_tick, records_this_tick)
                if state is None and (start_tick is None or tick > start_tick) and (
                        end_tick is None or tick <= end_tick):
                    initial_unknown = new[1] | new[2]
                    while initial_unknown:
                        low = initial_unknown & -initial_unknown
                        per_bit[low.bit_length()-1]['initial_unknown_bits'] += 1
                        initial_unknown -= low
                if state is not None and (start_tick is None or tick > start_tick) and (
                        end_tick is None or tick <= end_tick):
                    known = ((1 << width) - 1) & ~(state[1] | state[2] | new[1] | new[2])
                    changed = (state[0] ^ new[0]) | (state[1] ^ new[1]) | (state[2] ^ new[2])
                    toggles = (state[0] ^ new[0]) & known
                    unknown = changed & ~toggles
                    changed_copy = changed
                    while changed_copy:
                        low = changed_copy & -changed_copy
                        per_bit[low.bit_length()-1]['four_state_changes'] += 1
                        changed_copy -= low
                    while toggles:
                        low = toggles & -toggles
                        index = low.bit_length() - 1
                        per_bit[index]['known_toggles'] += 1
                        per_bit[index]['rises' if new[0] & low else 'falls'] += 1
                        toggles -= low
                    while unknown:
                        low = unknown & -unknown
                        per_bit[low.bit_length()-1]['unknown_changes'] += 1
                        unknown -= low
                state = new
            elif token[0] in '01xXzZ':
                ident = token[1:]
                if ident not in signals:
                    tokens.fail(f'Undeclared VCD identifier {ident}')
                if ident == bus_id:
                    tokens.fail('Scalar record for canonical bus')
            else:
                tokens.fail(f'Unsupported VCD record {token}')
        if dump or state is None or bus_records < 1:
            raise ValueError('Incomplete canonical mapped bus trace')
        if end_tick is not None and tick < end_tick:
            raise ValueError('Mapped trace ends before requested window')
        if start_tick is not None and start_tick >= tick:
            raise ValueError('Window starts at or beyond recorded trace end')
    categories = defaultdict(Counter)
    for entry, counts in zip(entries, per_bit):
        categories[entry['category']].update(counts)
    totals = Counter()
    for counts in per_bit:
        totals.update(counts)
    if validated['last_timestamp_tick'] != tick:
        raise ValueError('VCD validation timestamp mismatch')
    return dict(schema=1, timescale=scale, first_tick=first_tick, last_tick=tick,
                window=dict(start_exclusive_tick=start_tick, end_inclusive_tick=end_tick),
                canonical_bus_records=bus_records, max_bus_records_per_tick=max_per_tick,
                observed_net_bits=width,
                totals=dict(totals), categories={k: dict(v) for k, v in sorted(categories.items())},
                per_bit=per_bit)


def validate_port_bus(vcd, mapped, ledger):
    """Check every top-port bit against its canonical bus bit at every VCD time.

    Several zero-delay events may occur at one timestamp; check the settled
    end-of-timestamp state, then advance. No event is collapsed for counting.
    """
    analyze_vcd(vcd)
    top = mapped['modules']['dlgn_top']
    position = {entry['bit_id']: i for i, entry in enumerate(ledger['entries'])}
    with Path(vcd).open() as source:
        tokens = _Tokens(source)
        signals, _, _ = _header(tokens)
        selected = {}
        for name in list(PORTS) + ['activity_nodes']:
            matches = [signal for signal in signals.values() if any(
                alias['scope'] == ['tb_capture','dut'] and alias['reference'] == name
                for alias in signal['aliases'])]
            if len(matches) != 1:
                raise ValueError(f'Missing or ambiguous mapped VCD signal {name}')
            selected[name] = matches[0]
        if selected['activity_nodes']['width'] != len(position):
            raise ValueError('Canonical bus width differs from numeric net ledger')
        by_id = {signal['identifier']: signal['width'] for signal in selected.values()}
        state = {}
        timestamp = 0
        checked = 0

        def check(at):
            nonlocal checked
            if any(signal['identifier'] not in state for signal in selected.values()):
                raise ValueError(f'Mapped port/bus not fully initialized at {at}')
            bus = state[selected['activity_nodes']['identifier']]
            for name, port in top['ports'].items():
                value = state[selected[name]['identifier']]
                for offset, bit in enumerate(port['bits']):
                    port_mask = 1 << offset
                    actual = tuple(bool(part & port_mask) for part in value)
                    if type(bit) is int:
                        bus_mask = 1 << position[bit]
                        expected = tuple(bool(part & bus_mask) for part in bus)
                    else:
                        # Constants can appear on unconnected output bits.
                        expected = ((bit == '1'), (bit.lower() == 'x'), (bit.lower() == 'z'))
                    if actual != expected:
                        raise ValueError(f'Canonical bus disagrees with {name}[{offset}] at {at}')
            checked += 1

        started = False
        for token in iter(tokens.get, None):
            if token == '$comment':
                tokens.block()
            elif token.startswith('#'):
                following = int(token[1:])
                if started and following > timestamp:
                    check(timestamp)
                timestamp = following
                started = True
            elif token.startswith('$'):
                continue  # Already checked by the complete VCD parser.
            else:
                if token[0] in 'bB':
                    bits, ident = token[1:], tokens.need()
                else:
                    bits, ident = token[0], token[1:]
                if ident in by_id:
                    state[ident] = _state(bits, by_id[ident], tokens)
        if started:
            check(timestamp)
    return dict(checked_timestamps=checked, all_top_port_bits_checked=True,
                rule='Settled end of every recorded VCD timestamp; bus event count remains raw')
