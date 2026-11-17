"""Streaming digital VCD record counter; not a physical switching/power model.

Every identifier is counted once, retaining all declaration aliases. Counts
follow recorded file order, including multiple changes at one timestamp.
Initialization is an observation, never a transition. Changed bits touching
X/Z are separate from known 0<->1 toggles; no unknown value is coerced to zero.
"""
from decimal import Decimal
from pathlib import Path
import re


class VCDFormatError(ValueError):
    """Malformed or unsupported trace; no partial activity report is returned."""


DIGITAL_TYPES = {'wire', 'reg', 'integer', 'parameter', 'time', 'tri', 'tri0',
                 'tri1', 'triand', 'trior', 'trireg', 'wand', 'wor', 'supply0',
                 'supply1', 'logic', 'bit', 'int', 'shortint', 'longint', 'byte'}
COUNT_FIELDS = ('observed_records', 'initializations', 'initial_unknown_bits',
                'value_change_records', 'redundant_value_records',
                'known_bit_toggles', 'rises', 'falls', 'unknown_bit_changes',
                'four_state_bit_changes', 'unknown_value_records')


class _Tokens:
    def __init__(self, source):
        self.tokens = ((token, line_no) for line_no, line in enumerate(source, 1)
                       for token in line.split())
        self.line = 0

    def get(self):
        try:
            token, self.line = next(self.tokens)
            return token
        except StopIteration:
            return None

    def need(self):
        token = self.get()
        if token is None:
            self.fail('Unexpected end of VCD')
        return token

    def expect(self, expected):
        if self.need() != expected:
            self.fail(f'Expected {expected}')

    def fail(self, message):
        raise VCDFormatError(f'Line {self.line}: {message}')

    def block(self):
        values = []
        while (token := self.need()) != '$end':
            values.append(token)
        return values


def _header(tokens):
    scope, signals, paths = [], {}, set()
    timescale = None
    declaration_count = 0
    while True:
        directive = tokens.need()
        if directive in ('$date', '$version', '$comment'):
            tokens.block()
        elif directive == '$timescale':
            if timescale is not None:
                tokens.fail('Duplicate timescale')
            match = re.fullmatch(r'(1|10|100)(s|ms|us|ns|ps|fs)', ''.join(tokens.block()))
            if not match:
                tokens.fail('Unsupported timescale')
            magnitude, unit = int(match[1]), match[2]
            exponent = {'s': 0, 'ms': -3, 'us': -6, 'ns': -9, 'ps': -12, 'fs': -15}[unit]
            timescale = dict(magnitude=magnitude, unit=unit,
                             seconds_per_tick=str(Decimal(magnitude) * Decimal(10)**exponent))
        elif directive == '$scope':
            tokens.need()  # Scope type does not change transition semantics.
            scope.append(tokens.need())
            tokens.expect('$end')
        elif directive == '$upscope':
            if not scope:
                tokens.fail('Unbalanced scope')
            scope.pop()
            tokens.expect('$end')
        elif directive == '$var':
            kind, size, identifier, reference = (tokens.need() for _ in range(4))
            if kind not in DIGITAL_TYPES:
                tokens.fail(f'Unsupported variable type {kind}')
            if not size.isdecimal() or int(size) <= 0:
                tokens.fail('Invalid signal width')
            width = int(size)
            extra = tokens.need()
            bit_index = None
            if extra != '$end':
                if not re.fullmatch(r'\[-?\d+(?::-?\d+)?\]', extra):
                    tokens.fail('Unsupported variable range')
                bit_index = extra
                tokens.expect('$end')
            path = '.'.join(scope + [reference]) + (bit_index or '')
            if path in paths:
                tokens.fail(f'Duplicate declaration path {path}')
            paths.add(path)
            if identifier not in signals:
                signals[identifier] = dict(identifier=identifier, width=width, aliases=[],
                                           counts={key: 0 for key in COUNT_FIELDS})
            signal = signals[identifier]
            if signal['width'] != width:
                tokens.fail(f'Incompatible alias widths for {identifier}')
            signal['aliases'].append(dict(path=path, scope=list(scope), reference=reference,
                                          bit_index=bit_index, type=kind))
            declaration_count += 1
        elif directive == '$enddefinitions':
            tokens.expect('$end')
            if scope or timescale is None or not signals:
                tokens.fail('Incomplete scopes, timescale or declarations')
            return signals, timescale, declaration_count
        else:
            tokens.fail(f'Unsupported header directive {directive}')


def _state(bits, width, tokens):
    """Return known-one, X and Z bit masks after VCD left-extension."""
    bits = bits.lower()
    if not bits or re.search('[^01xz]', bits) or len(bits) > width:
        tokens.fail('Invalid binary value or width overflow')
    if 'x' not in bits and 'z' not in bits:
        return int(bits, 2), 0, 0
    pad = bits[0] if bits[0] in 'xz' else '0'
    bits = bits.rjust(width, pad)
    ones = int(''.join('1' if bit == '1' else '0' for bit in bits), 2)
    xs = int(''.join('1' if bit == 'x' else '0' for bit in bits), 2)
    zs = int(''.join('1' if bit == 'z' else '0' for bit in bits), 2)
    return ones, xs, zs


def analyze_vcd(path, start_tick=None, end_tick=None):
    """Count recorded changes once per identifier over optional (start,end].

    With start=None all timestamps, including initialization at t=0, are
    included. Explicit start=0 excludes records at t=0 but carries their state
    into the interval. All pre-start records update state without contributing
    counts. Bounds use the file's integer timescale ticks, not assumed ns/ps.
    The whole file is parsed/validated even with an early end boundary.

    Supported: whitespace-delimited digital declarations, binary/scalar value
    records, integer timestamps, comments, dumpvars and dumpall snapshots.
    Real/string/event variables and dumping suspension are rejected, not
    silently omitted. This is deliberately narrower than the full VCD family.
    """
    for boundary in (start_tick, end_tick):
        if boundary is not None and (type(boundary) is not int or boundary < 0):
            raise ValueError('Window bounds must be nonnegative integer ticks')
    if start_tick is not None and end_tick is not None and start_tick >= end_tick:
        raise ValueError('Window requires start < end')
    with Path(path).open() as source:
        tokens = _Tokens(source)
        signals, timescale, declarations = _header(tokens)
        states = {}
        timestamp, dump_block, first_timestamp = 0, None, None
        while (token := tokens.get()) is not None:
            if token == '$comment':
                tokens.block()
                continue
            if token in ('$dumpvars', '$dumpall'):
                if dump_block is not None:
                    tokens.fail('Nested dump blocks')
                dump_block = token
                continue
            if token == '$end':
                if dump_block is None:
                    tokens.fail('Unexpected $end in value section')
                dump_block = None
                continue
            if token.startswith('#'):
                if dump_block is not None:
                    tokens.fail('Timestamp inside dump block')
                if not token[1:].isdecimal():
                    tokens.fail('Expected integer timestamp')
                following = int(token[1:])
                if following < timestamp:
                    tokens.fail('Timestamp moved backwards')
                timestamp = following
                if first_timestamp is None:
                    first_timestamp = timestamp
                continue
            if token.startswith('$'):
                tokens.fail(f'Unsupported value directive {token}; dumping must remain continuous')
            if token[0] in 'bB':
                bits, identifier = token[1:], tokens.need()
                scalar = False
            elif token[0] in '01xXzZ':
                bits, identifier, scalar = token[0], token[1:], True
            else:
                tokens.fail(f'Unsupported value record {token}')
            if identifier not in signals:
                tokens.fail(f'Undeclared identifier {identifier}')
            signal = signals[identifier]
            if scalar and signal['width'] != 1:
                tokens.fail('Scalar record for a multi-bit signal')
            new = _state(bits, signal['width'], tokens)
            old = states.get(identifier)
            states[identifier] = new
            if first_timestamp is None:
                first_timestamp = timestamp
            if (start_tick is not None and timestamp <= start_tick) or (
                    end_tick is not None and timestamp > end_tick):
                continue
            counts = signal['counts']
            counts['observed_records'] += 1
            new_unknown = new[1] | new[2]
            if new_unknown:
                counts['unknown_value_records'] += 1
            if old is None:
                counts['initializations'] += 1
                counts['initial_unknown_bits'] += new_unknown.bit_count()
                continue
            if old == new:
                counts['redundant_value_records'] += 1
                continue
            counts['value_change_records'] += 1
            old_unknown = old[1] | old[2]
            mask = (1 << signal['width']) - 1
            known = mask & ~(old_unknown | new_unknown)
            toggles = (old[0] ^ new[0]) & known
            rises = toggles & new[0]
            changed = (old[0] ^ new[0]) | (old[1] ^ new[1]) | (old[2] ^ new[2])
            counts['known_bit_toggles'] += toggles.bit_count()
            counts['rises'] += rises.bit_count()
            counts['falls'] += toggles.bit_count() - rises.bit_count()
            counts['four_state_bit_changes'] += changed.bit_count()
            counts['unknown_bit_changes'] += changed.bit_count() - toggles.bit_count()
        if dump_block is not None:
            tokens.fail('Unclosed dump block')
        if any(bound is not None and bound > timestamp for bound in (start_tick, end_tick)):
            raise ValueError('Window extends beyond recorded trace')
    return dict(schema=1, timescale=timescale,
                first_timestamp_tick=first_timestamp, last_timestamp_tick=timestamp,
                window=dict(start_exclusive_tick=start_tick, end_inclusive_tick=end_tick,
                            policy='All records if unbounded; otherwise (start,end], with carried state'),
                declaration_count=declarations, unique_identifier_count=len(signals),
                identifiers_without_values=sorted(set(signals)-set(states)),
                totals={key: sum(signal['counts'][key] for signal in signals.values())
                        for key in COUNT_FIELDS}, signals=list(signals.values()),
                interpretation='Digital recorded-event diagnostics, including same-timestamp events; '
                               'not settled logical transitions, physical glitches, or power/energy')
