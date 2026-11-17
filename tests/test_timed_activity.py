"""Step 3.9 timed-activity checks: SDF renaming, net ledger, counters, glitch arithmetic."""
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import capture_timed_activity as cta  # noqa: E402

PARAMS = dict(IN=8, K=1, SW=1, CW=1)


def routed(cells):
    return dict(modules=dict(top=dict(ports=dict(o=dict(direction='output', bits=[9])),
                                      cells=cells, netnames={})))


def lc(conn, dirs, ctype='ICESTORM_LC'):
    return dict(type=ctype, connections=conn, port_directions=dirs, parameters={})


def test_rename_rewrites_escaped_instances_and_interconnects():
    cells = {'board.adapter.core.sc_reg[0]_LC': lc({}, {}), '$nextpnr_ICESTORM_LC_1': lc({}, {})}
    sdf = ('(DELAYFILE\n (CELL\n  (INSTANCE )\n  (DELAY (ABSOLUTE\n'
           '   (INTERCONNECT \\$nextpnr_ICESTORM_LC_1/COUT board.adapter.core.sc_reg\\[0\\]_LC/I3 (1:1:1))\n'
           '  ))\n )\n (CELL\n  (CELLTYPE "ICESTORM_LC")\n  (INSTANCE board.adapter.core.sc_reg\\[0\\]_LC)\n )\n)\n')
    renamed, text, counts, simple = cta.rename_design(routed(cells), sdf)
    assert simple == {'$nextpnr_ICESTORM_LC_1': 'c0', 'board.adapter.core.sc_reg[0]_LC': 'c1'}
    assert set(renamed['modules']['top']['cells']) == {'c0', 'c1'}
    assert '(INTERCONNECT c0/COUT c1/I3 (1:1:1))' in text and '(INSTANCE c1)' in text
    assert counts == dict(instance=1, interconnect=1)
    assert '\\' not in text


@pytest.mark.parametrize('line', ['  (INTERCONNECT nope/O c/I0 (1:1:1))\n',
                                  '  (INSTANCE \\$unknown)\n',
                                  '  (INTERCONNECT malformed)\n'])
def test_rename_rejects_unknown_or_unparsed_names(line):
    with pytest.raises(ValueError):
        cta.rename_design(routed({'c': lc({}, {})}), f'(DELAYFILE\n{line})\n')


def test_net_ledger_dedups_skips_unloaded_and_categorizes():
    cells = {
        'c0': lc({'O': [5], 'LO': [6], 'I0': [7]}, {'O': 'output', 'LO': 'output', 'I0': 'input'}),
        'c1': lc({'O': [7], 'I0': [5]}, {'O': 'output', 'I0': 'input'}),
        'c2': lc({'GLOBAL_BUFFER_OUTPUT': [8], 'USER_SIGNAL_TO_GLOBAL_BUFFER': [9]},
                 {'GLOBAL_BUFFER_OUTPUT': 'output', 'USER_SIGNAL_TO_GLOBAL_BUFFER': 'input'}, 'SB_GB'),
        'c3': lc({'O': [9], 'I0': [8]}, {'O': 'output', 'I0': 'input'}),
        'c5': lc({'GLOBAL_BUFFER_OUTPUT': [10], 'USER_SIGNAL_TO_GLOBAL_BUFFER': [11]},
                 {'GLOBAL_BUFFER_OUTPUT': 'output', 'USER_SIGNAL_TO_GLOBAL_BUFFER': 'input'}, 'SB_GB'),
        'c6': lc({'D_IN_0': [11], 'I0': [10]}, {'D_IN_0': 'output', 'I0': 'input'}, 'SB_IO'),
    }
    design = routed(cells)
    design['modules']['top']['netnames'] = {
        'board.adapter.core.l1_c': dict(bits=[5]), 'board.adapter.reply': dict(bits=[7]),
        '$auto$x': dict(bits=[9]), '$gbuf_clk$SB_IO_IN_$glb_clk': dict(bits=[10]),
        'clk$SB_IO_IN': dict(bits=[11])}
    entries = cta.net_ledger(design)
    assert [(e['driver'], e['category']) for e in entries] == [
        ('c0.O', 'core'), ('c1.O', 'interface'), ('c2.GLOBAL_BUFFER_OUTPUT', 'global_buffer'),
        ('c3.O', 'unclassified'), ('c5.GLOBAL_BUFFER_OUTPUT', 'clock'), ('c6.D_IN_0', 'clock')]
    cells['c4'] = lc({'O': [5]}, {'O': 'output'})
    with pytest.raises(ValueError, match='drivers'):
        cta.net_ledger(design)


def test_summarize_reports_extra_and_detects_inconsistency():
    entries = [dict(driver='a.O', category='core'), dict(driver='b.O', category='interface')]
    clock = [dict(driver='k.O', category='clock')]
    edges = [dict(transitions=10, unknown_changes=0, settled=0, settled_unknown=0)]
    cats, totals, _ = cta.summarize(clock, edges, edges)
    assert cats['clock']['extra_transitions'] == 10 and totals.get('extra_transitions', 0) == 0
    timed = [dict(transitions=7, unknown_changes=0, settled=3, settled_unknown=0),
             dict(transitions=2, unknown_changes=0, settled=2, settled_unknown=0)]
    untimed = [dict(transitions=3, unknown_changes=0, settled=3, settled_unknown=0),
               dict(transitions=2, unknown_changes=0, settled=2, settled_unknown=0)]
    cats, totals, problems = cta.summarize(entries, timed, untimed)
    assert problems == []
    assert cats['core']['extra_transitions'] == 4 and cats['core']['extra_per_settled'] == 4/3
    assert totals['extra_transitions'] == 4 and totals['settled_changes'] == 5
    odd = [dict(timed[0], transitions=6), timed[1]]
    assert cta.summarize(entries, odd, untimed)[2] == ['parity/negative extra a.O']
    moved = [untimed[0], dict(untimed[1], settled=1)]
    assert cta.summarize(entries, timed, moved)[2] == ['settled mismatch b.O']


HAZARD = r'''
`timescale 1ps/1ps
module dff_d(input C, D, output reg Q); initial Q = 0; always @(posedge C) Q <= D;
  specify (posedge C => (Q : D)) = (1000, 1000); endspecify endmodule
module inv_d(input A, output Y); assign Y = ~A; specify (A => Y) = (200, 200); endspecify endmodule
module buf_d(input A, output Y); assign Y = A; specify (A => Y) = (`SLOW, `SLOW); endspecify endmodule
module xor_d(input A, B, output Y); assign Y = A ^ B;
  specify (A => Y) = (500, 500); (B => Y) = (500, 500); endspecify endmodule
module top(output uart_tx_pin, input uart_rx_pin, input clk, input button_n);
  wire q, qn, qd, y;
  dff_d f(.C(clk), .D(qn), .Q(q)); inv_d i(.A(q), .Y(qn));
  buf_d b(.A(q), .Y(qd)); xor_d x(.A(q), .B(qd), .Y(y));
  assign uart_tx_pin = 1'b1;
endmodule
'''
ENTRIES = [dict(driver=d) for d in ('f.Q', 'i.Y', 'b.Y', 'x.Y')]


def run_hazard(tmp_path, timed, slow=3000, cycles=20):
    if not shutil.which('iverilog'):
        pytest.skip('iverilog required')
    (tmp_path/'dut.v').write_text(HAZARD)
    (tmp_path/'tb.sv').write_text(cta.testbench(ENTRIES, 0, PARAMS, 4, idle_cycles=cycles))
    flags = ['-gspecify'] if timed else []
    subprocess.run(['iverilog', '-g2012', *flags, f'-DSLOW={slow}', '-o', 'simv', 'tb.sv', 'dut.v'],
                   cwd=tmp_path, check=True, capture_output=True)
    out = subprocess.run(['vvp', '-n', 'simv'], cwd=tmp_path, check=True,
                         capture_output=True, text=True).stdout
    assert 'PASS: 0/0' in out
    return cta.parse_counts(tmp_path/'counts.txt', len(ENTRIES))


def test_known_hazard_counts_timed_and_untimed(tmp_path):
    (tmp_path/'t').mkdir()
    (tmp_path/'u').mkdir()
    tmeta, timed = run_hazard(tmp_path/'t', True)
    umeta, untimed = run_hazard(tmp_path/'u', False)
    s = tmeta['samples']
    assert s == umeta['samples'] and s >= 20 and tmeta['replies'] == 0
    # q, qn and qd toggle once per cycle; the XOR pulses 0->1->0 (2500 ps wide) each cycle.
    assert [c['transitions'] for c in timed] == [s, s, s, 2*s]
    assert [c['settled'] for c in timed] == [s, s, s, 0]
    assert [c['settled'] for c in untimed] == [s, s, s, 0]
    assert all(c['unknown_changes'] == 0 and c['settled_unknown'] == 0 for c in timed)
    assert tmeta['max_offset_ps'] == 1000 + 3000 + 500 and tmeta['late_events'] == 0
    entries = [dict(e, category='core') for e in ENTRIES]
    _, totals, problems = cta.summarize(entries, timed, untimed)
    assert problems == [] and totals['extra_transitions'] == 2*s


def test_late_event_in_guard_band_is_reported(tmp_path):
    # 80 ns buffer: the XOR's second edge lands within 10 ns of the next sample.
    meta, _ = run_hazard(tmp_path, True, slow=80000)
    assert meta['late_events'] > 0


def test_capture_rejects_bad_image_count():
    for n in (0, 451, 1.5):
        with pytest.raises(ValueError):
            cta.capture(n)


PULSE = r'''
`timescale 1ps/1ps
module buf_d(input A, output Y); assign Y = A; specify (A => Y) = (500, 500); endspecify endmodule
module top(input a, output y_mod, output y_ic);
  buf_d m(.A(a), .Y(y_mod)); buf_d n(.A(a), .Y(y_ic));
endmodule
module tb; reg a = 0; wire ym, yi; integer cm = 0, ci = 0;
  top dut(.a(a), .y_mod(ym), .y_ic(yi));
  always @(ym) if ($time > 1000) cm = cm + 1;
  always @(yi) if ($time > 1000) ci = ci + 1;
  initial begin $sdf_annotate("pulse.sdf", dut);
    #2000 a = 1; #200 a = 0;    // 200 ps: < 500 ps module path, < 300 ps interconnect
    #3000 a = 1; #50 a = 0;     // 50 ps
    #3000 a = 1; #800 a = 0;    // 800 ps: wider than every path
    #5000 $display("COUNTS %0d %0d", cm, ci); end
endmodule
'''
PULSE_SDF = '''(DELAYFILE (SDFVERSION "3.0") (DESIGN "top") (DIVIDER /) (TIMESCALE 1ps)
 (CELL (CELLTYPE "top") (INSTANCE ) (DELAY (ABSOLUTE (INTERCONNECT a n/A (300:300:300) (300:300:300)))))
 (CELL (CELLTYPE "buf_d") (INSTANCE n) (DELAY (ABSOLUTE (IOPATH A Y (100:100:100) (100:100:100))))))
'''


def test_icarus_filters_narrow_pulses_inertially(tmp_path):
    """Documents the 3.9 glitch semantics: pulses narrower than a path delay vanish."""
    if not shutil.which('iverilog'):
        pytest.skip('iverilog required')
    (tmp_path/'pulse.v').write_text(PULSE)
    (tmp_path/'pulse.sdf').write_text(PULSE_SDF)
    subprocess.run(['iverilog', '-g2012', '-gspecify', '-ginterconnect', '-o', 'p', 'pulse.v'],
                   cwd=tmp_path, check=True, capture_output=True)
    out = subprocess.run(['vvp', '-n', 'p'], cwd=tmp_path, check=True, capture_output=True, text=True).stdout
    # Only the 800 ps pulse survives: 2 edges on each path (module path; 300 ps interconnect + 100 ps cell).
    assert 'COUNTS 2 2' in out
