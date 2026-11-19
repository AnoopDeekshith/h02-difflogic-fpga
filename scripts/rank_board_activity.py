"""Step 4.11 (first part): rank routed-board switching by functional block.

Read-only analysis of the archived step 3.9 SDF-timed UART-board capture
(8 requests, 12 MHz, 104 clocks/bit). Groups per-net timed transitions and
settled changes into blocks (clock, DLGN core, UART counters split into
register bits and next-state logic, ...) to identify where Gray coding or
other recoding could matter. Transition counts are not energy: per-net
capacitance differs greatly (the clock drives every flip-flop).

  python scripts/rank_board_activity.py runs/step3.9-glitch/timed-activity.0hvnej44 \
      --out docs/results/step-4.11-board-activity-ranking.json
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re

COUNTERS = (('idle_count', 'idle_count'), ('receiver.timer', 'rx_timer'),
            ('transmitter.timer', 'tx_timer'))
# Nets whose names do not reveal their counter, assigned from routed connectivity
# (docs/reviews/step-4.11-ranking-review.md). Applied only to the step 3.9
# ledger with this exact hash; other captures need their own review.
LEDGER_SHA256 = '69b09e83952e2a04bccdf157d2fe324806cdfc450007b46bc30fcb1ed8834d97'
OVERRIDES = {
    'c4006.O': 'rx_timer.register',      # RX timer bits 4-6: share its clock enable,
    'c3998.O': 'rx_timer.register',      # end its carry chain and feed back to
    'c3999.O': 'rx_timer.register',      # themselves; named receiver.state_*
    'c24.COUT': 'idle_count.carry_entry',  # bit 0 into the counter carry chains
    'c6.COUT': 'rx_timer.carry_entry',
    'c26.COUT': 'tx_timer.carry_entry',
}
REGISTER = re.compile(r'board\.adapter\.(receiver\.|transmitter\.)?(idle_count|timer)\[\d+\]')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_counts(path, n):
    lines = Path(path).read_text().splitlines()
    rows = [list(map(int, line.split())) for line in lines[1:]]
    if len(rows) != n or [r[0] for r in rows] != list(range(n)):
        raise ValueError('Count file does not match the net ledger')
    return lines[0], rows


def block(entry, overrides=None):
    """Functional block of one net (heuristic names; step 3.9 categories first)."""
    if overrides and entry['driver'] in overrides:
        return overrides[entry['driver']]
    if entry['category'] in ('clock', 'global_buffer', 'io'):
        return entry['category']
    if entry['category'] == 'core':
        return 'core'
    visible = [n for n in entry['names'] if not n.startswith('$')]
    text = ' '.join(visible)
    for key, label in COUNTERS:
        if key in text:
            kind = 'register' if any(REGISTER.fullmatch(v) for v in visible) else 'next_state_logic'
            return f'{label}.{kind}'
    for key, label in (('receiver', 'rx_other'), ('transmitter', 'tx_other')):
        if key in text:
            return label
    return 'unclassified' if entry['category'] == 'unclassified' else 'interface_other'


def rank(capture):
    capture = Path(capture)
    ledger = json.loads((capture/'net-ledger.json').read_text())
    header, rows = read_counts(capture/'counts_timed.txt', len(ledger))
    overrides = OVERRIDES if digest(capture/'net-ledger.json') == LEDGER_SHA256 else {}
    present = {e['driver'] for e in ledger}
    if overrides and not set(overrides) <= present:
        raise ValueError('Override drivers missing from the ledger')
    blocks = collections.defaultdict(lambda: dict(nets=0, timed=0, settled=0))
    unclassified = []
    for entry, row in zip(ledger, rows):
        b = block(entry, overrides)
        blocks[b]['nets'] += 1
        blocks[b]['timed'] += row[1]
        blocks[b]['settled'] += row[3]
        if b == 'unclassified' and row[1]:
            unclassified.append(dict(names=entry['names'], driver=entry['driver'],
                                     timed=row[1], settled=row[3]))
    total = sum(v['timed'] for v in blocks.values())
    clock_global = sum(r[1] for e, r in zip(ledger, rows) if e['category'] == 'clock'
                       and e['driver'].endswith('GLOBAL_BUFFER_OUTPUT'))
    groups = {g: sum(v['timed'] for k, v in blocks.items() if k.startswith(g+'.'))
              for g in ('idle_count', 'rx_timer', 'tx_timer')}
    counter_regs = sum(v['timed'] for k, v in blocks.items() if k.endswith('.register'))
    ordered = sorted(blocks.items(), key=lambda kv: -kv[1]['timed'])
    return dict(
        source=str(capture), header=header, total_timed_transitions=total,
        overrides_applied=sorted(overrides),
        clock_note='The clock appears twice (pad net and global net, same signal); total_with_clock_once removes one of the two identical copies.',
        total_with_clock_once=total - clock_global,
        summary=dict(clock_share=sum(v['timed'] for k, v in blocks.items() if k == 'clock')/total,
                     core_share=blocks['core']['timed']/total,
                     counters_share=sum(groups.values())/total,
                     counter_register_share=counter_regs/total,
                     counters=groups),
        files_sha256={n: digest(capture/n) for n in ('net-ledger.json', 'counts_timed.txt', 'result.json')},
        blocks=[dict(block=k, share=v['timed']/total, **v) for k, v in ordered],
        unclassified_top=sorted(unclassified, key=lambda u: -u['timed'])[:10])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('capture')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    result = rank(a.capture)
    Path(a.out).write_text(json.dumps(result, indent=2)+'\n')
    for b in result['blocks']:
        print(f"{100*b['share']:5.1f}%  timed {b['timed']:8d}  settled {b['settled']:8d}  nets {b['nets']:5d}  {b['block']}")


if __name__ == '__main__':
    main()
