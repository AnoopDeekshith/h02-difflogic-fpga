"""Step 3.9: SDF-annotated glitch estimate on the routed iCE40 UART board.

Re-runs nextpnr on the archived, verified head-only UART implementation with
SDF output and requires a bit-identical bitstream. Instances are renamed so
Icarus can parse the SDF. One generated testbench drives N clean UART
transactions at 12 MHz with the hardware divider, checks every reply byte
against NumPy, and counts, for every driven net bit:

* transitions while the window is open (known 0/1 and X/Z-involving separately)
* settled changes, sampled 1 ps before each rising clock edge

The same netlist runs twice: with SDF delays (timed) and with zero-delay
primitives (untimed). Settled values must agree. Extra timed transitions,
transitions minus settled changes, are the glitch estimate.

Icarus applies module-path and interconnect delays inertially: pulses shorter
than a path delay are swallowed. Single corner nextpnr-SDF delay estimate; not
measured glitches, power or energy.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
from dlgn import hard  # noqa: E402
from dlgn.export_verilog import emit_rtl, write_vectors  # noqa: E402
from check_waveform_recording import digest  # noqa: E402

EXPORT = ROOT/'runs/digits_w1000/uart_comb_head'
IMPLEMENTATION = EXPORT/'implementation.UVAx2g'
MODEL_RUN = ROOT/'runs/digits_w1000'
OUT_ROOT = ROOT/'runs/step3.9-glitch'
HALF_PS = 41667            # 12 MHz nominal, 1 ps quantized: period 83,334 ps
GUARD_PS = 10000           # no event may land in the last 10 ns before a sample
NEXTPNR_ARGS = ['--up5k', '--package', 'sg48', '--freq', '12', '--seed', '1',
                '--json', 'synth_uart.json', '--pcf', 'icebreaker_uart.pcf',
                '--sdc', 'icebreaker_uart.sdc', '--asc', 'routed_uart.asc',
                '--write', 'routed_uart.json', '--sdf', 'routed.sdf']
SOURCE_FILES = (Path(__file__).resolve(), ROOT/'dlgn/hard.py', ROOT/'dlgn/gates.py',
                ROOT/'dlgn/export_verilog.py', ROOT/'scripts/check_waveform_recording.py')


def sdf_escape(name):
    """nextpnr's SDF spelling: escape everything except [A-Za-z0-9_.]."""
    return re.sub(r'([^A-Za-z0-9_.])', r'\\\1', name)


def rename_design(routed, sdf_text):
    """Give every routed cell a simple name, consistently in JSON and SDF.

    Fail if any SDF instance or interconnect endpoint is not a known cell.
    """
    top = routed['modules']['top']
    names = sorted(top['cells'])
    simple = {name: f'c{i}' for i, name in enumerate(names)}
    by_escaped = {sdf_escape(name): simple[name] for name in names}
    if len(by_escaped) != len(names):
        raise ValueError('SDF escaping collides for distinct cell names')
    renamed = json.loads(json.dumps(routed))
    renamed['modules']['top']['cells'] = {simple[n]: c for n, c in top['cells'].items()}
    lines, rewritten = [], Counter()

    def lookup(token):
        if token not in by_escaped:
            raise ValueError(f'SDF names unknown cell {token}')
        return by_escaped[token]

    for line in sdf_text.splitlines(keepends=True):
        inst = re.match(r'(\s*\(INSTANCE )(\S*)\)(\s*)$', line)
        conn = re.match(r'(\s*\(INTERCONNECT )(\S+)/(\S+) (\S+)/(\S+) (.*)$', line, re.S)
        if inst and inst.group(2):
            line = f'{inst.group(1)}{lookup(inst.group(2))}){inst.group(3)}'
            rewritten['instance'] += 1
        elif conn:
            line = (f'{conn.group(1)}{lookup(conn.group(2))}/{conn.group(3)} '
                    f'{lookup(conn.group(4))}/{conn.group(5)} {conn.group(6)}')
            rewritten['interconnect'] += 1
        elif 'INTERCONNECT' in line or ('INSTANCE' in line and '(INSTANCE )' not in line):
            raise ValueError(f'Unparsed SDF line: {line.strip()[:80]}')
        lines.append(line)
    return renamed, ''.join(lines), dict(rewritten), simple


CLOCK_NAME = re.compile(r'(^|[.$])clk($|[$\[])|\$glb_clk$')


def category(names, cell_type):
    # The clock toggles twice per sampled cycle by design: never a glitch.
    if any(CLOCK_NAME.search(n) for n in names):
        return 'clock'
    if cell_type == 'SB_GB':
        return 'global_buffer'
    if cell_type == 'SB_IO':
        return 'io'
    visible = [n for n in names if not n.startswith('$')] or names
    if any(n.startswith('board.adapter.core.') for n in visible):
        return 'core'
    if any(n.startswith('board.') for n in visible):
        return 'interface'
    return 'unclassified'


def net_ledger(renamed):
    """One entry per numeric net bit driven by a cell output and used elsewhere."""
    top = renamed['modules']['top']
    drivers, loads = defaultdict(list), Counter()
    for cname, cell in top['cells'].items():
        for pin, bits in cell['connections'].items():
            for bit in bits:
                if type(bit) is not int:
                    continue
                if cell['port_directions'][pin] == 'output':
                    drivers[bit].append((cname, pin, cell['type']))
                else:
                    loads[bit] += 1
    for port in top['ports'].values():
        for bit in port['bits']:
            if type(bit) is int and port['direction'] == 'output':
                loads[bit] += 1
    names = defaultdict(list)
    for nname, net in top.get('netnames', {}).items():
        for offset, bit in enumerate(net['bits']):
            if type(bit) is int:
                names[bit].append(nname if len(net['bits']) == 1 else f'{nname}[{offset}]')
    entries = []
    for bit in sorted(drivers):
        if len(drivers[bit]) != 1:
            raise ValueError(f'Net bit {bit} has {len(drivers[bit])} drivers')
        cname, pin, ctype = drivers[bit][0]
        if not loads[bit]:
            continue  # unloaded output (for example an unused LO pin)
        if not re.fullmatch(r'c\d+', cname) or not re.fullmatch(r'[A-Z_0-9]+', pin):
            raise ValueError(f'Unexpected driver reference {cname}.{pin}')
        entries.append(dict(bit_id=bit, driver=f'{cname}.{pin}', cell_type=ctype,
                            category=category(sorted(names[bit]), ctype),
                            names=sorted(names[bit])[:4]))
    if not entries:
        raise ValueError('No driven nets to observe')
    return entries


def testbench(entries, n_images, params, cpb, idle_cycles=None):
    """Generate the UART stimulus/checker plus per-net transition counters.

    With idle_cycles (tests only), no UART traffic is sent: the window stays
    open for that many clock cycles and no replies are expected.
    """
    if idle_cycles is not None:
        n_images = 0
    m = len(entries)
    in_bytes = (params['IN'] + 7)//8
    out = [f'''`timescale 1ps/1ps
module tb_timed;
  localparam N={max(n_images, 1)}, NREQ={n_images}, IN={params['IN']}, K={params['K']}, SW={params['SW']};
  localparam CW={params['CW']}, CPB={cpb}, HALF={HALF_PS}, M={m}, GUARD={GUARD_PS};
  localparam INPUT_BYTES={in_bytes}, REPLY_BYTES=K+3;
  // Pins start X and get their values at 1 ps: the SB_IO model only
  // updates D_IN_0 on a pin change, so time-0 values would never propagate.
  reg clk=0, button_n=1'bx, rx=1'bx; wire tx;
  top dut(.uart_tx_pin(tx), .uart_rx_pin(rx), .clk(clk), .button_n(button_n));
  always #HALF clk = ~clk;
  reg [IN-1:0] xmem [0:N-1]; reg [K*SW-1:0] smem [0:N-1]; reg [CW-1:0] cmem [0:N-1];
  integer nout=0, rindex=0, f, k;
  integer cycles=0;
  always @(posedge clk) begin cycles = cycles + 1;
    if (cycles > (NREQ+2)*60000 + {idle_cycles or 0} + 20000) $fatal(1, "Timeout: %0d/%0d replies", nout, NREQ); end
  reg [7:0] rbyte, ebyte;
  reg win=0, open_req=0, close_req=0, closed=0;
  time last_edge=0, max_offset=0, offset;
  integer late=0, samples=0;
  integer tr [0:M-1]; integer unk [0:M-1]; integer st [0:M-1]; integer stunk [0:M-1];
  reg pv [0:M-1]; reg sv [0:M-1];
  always @(posedge clk) last_edge = $time;
  task automatic send_byte(input [7:0] value);
    @(negedge clk); rx=0; repeat(CPB) @(negedge clk);
    for (integer b=0; b<8; b=b+1) begin rx=value[b]; repeat(CPB) @(negedge clk); end
    rx=1; repeat(CPB) @(negedge clk);
  endtask
  initial begin
    forever begin
      @(negedge tx);
      if (button_n) begin
        repeat(CPB + CPB/2) @(negedge clk);
        for (integer b=0; b<8; b=b+1) begin rbyte[b]=tx; repeat(CPB) @(negedge clk); end
        if (tx !== 1'b1) $fatal(1, "TX stop bit invalid");
        if (nout >= NREQ) $fatal(1, "Unexpected extra reply");
        if (rindex == 0) ebyte = 8'h5a; else if (rindex == 1) ebyte = 8'ha5;
        else if (rindex == 2) ebyte = 8'(cmem[nout]);
        else ebyte = 8'(smem[nout] >> ((rindex-3)*SW)) & ((1<<SW)-1);
        if (rbyte !== ebyte) $fatal(1, "Reply %0d byte %0d: got %h expected %h", nout, rindex, rbyte, ebyte);
        if (rindex == REPLY_BYTES-1) begin rindex=0; nout=nout+1; end else rindex=rindex+1;
      end
    end
  end
  initial begin
`ifdef SDF
    $sdf_annotate("renamed.sdf", dut);
`endif
    #1 button_n = 0; rx = 1;
    if (NREQ > 0) begin $readmemh("x.hex", xmem); $readmemh("exp_scores.hex", smem); $readmemh("exp_class.hex", cmem); end
    for (k=0; k<M; k=k+1) begin tr[k]=0; unk[k]=0; st[k]=0; stunk[k]=0; end
    repeat(8) @(negedge clk); button_n = 1; repeat(CPB*4) @(negedge clk);
    open_req = 1; wait(win);
    repeat({idle_cycles or 0}) @(negedge clk);
    for (integer n=0; n<NREQ; n=n+1) begin
      send_byte(8'ha5); send_byte(8'h5a);
      for (integer j=0; j<INPUT_BYTES; j=j+1) send_byte(8'(xmem[n] >> (8*j)));
      wait(nout == n+1); repeat(CPB*2) @(negedge clk);
    end
    close_req = 1; wait(closed);
    f = $fopen("counts.txt", "w");
    $fwrite(f, "# samples %0d max_offset_ps %0d late_events %0d replies %0d\\n", samples, max_offset, late, nout);
    for (k=0; k<M; k=k+1) $fwrite(f, "%0d %0d %0d %0d %0d\\n", k, tr[k], unk[k], st[k], stunk[k]);
    $fclose(f);
    if (nout != NREQ) $fatal(1, "Wrong reply count");
    $display("PASS: %0d/%0d timed-netlist UART replies bit-exact (scores + class)", nout, NREQ);
    $finish;
  end
  // Window boundaries are sample points 1 ps before rising edges. Settled
  // changes are committed lazily: when a net's event lands in a later cycle,
  // its value at every boundary since its last event was pv, so one change
  // is counted if pv differs from the last committed boundary value sv.
  time t_open=0; time cyc [0:M-1]; time c;
  always @(posedge clk) begin
    #(2*HALF-1);
    if (win) begin
      samples = samples + 1;
      if (close_req) begin
`define FINAL(I, S) if ((sv[I] ^ S) === 1'b1) st[I] = st[I] + 1; else if ((sv[I] ^ S) !== 1'b0) stunk[I] = stunk[I] + 1;
''']
    for i, e in enumerate(entries):
        out.append(f'        `FINAL({i}, dut.{e["driver"]})\n')
    out.append('''        win = 0; closed = 1;
      end
    end else if (open_req && !closed) begin
      t_open = $time;
''')
    for i, e in enumerate(entries):
        out.append(f'      sv[{i}] = dut.{e["driver"]}; pv[{i}] = dut.{e["driver"]}; cyc[{i}] = 0;\n')
    out.append('''      win = 1;
    end
  end
`define WATCH(I, S) always @(S) begin if (win) begin c = ($time - t_open) / (2*HALF); if (c > cyc[I]) begin if ((sv[I] ^ pv[I]) === 1'b1) st[I] = st[I] + 1; else if ((sv[I] ^ pv[I]) !== 1'b0) stunk[I] = stunk[I] + 1; sv[I] = pv[I]; cyc[I] = c; end if ((pv[I] ^ S) === 1'bx) unk[I] = unk[I] + 1; else tr[I] = tr[I] + 1; offset = $time - last_edge; if (offset > max_offset) max_offset = offset; if (offset > 2*HALF - GUARD) late = late + 1; end pv[I] = S; end
''')
    for i, e in enumerate(entries):
        out.append(f'  `WATCH({i}, dut.{e["driver"]})\n')
    out.append('endmodule\n')
    return ''.join(out)


def parse_counts(path, m):
    lines = Path(path).read_text().splitlines()
    head = lines[0].split()
    meta = dict(samples=int(head[2]), max_offset_ps=int(head[4]),
                late_events=int(head[6]), replies=int(head[8]))
    rows = [list(map(int, line.split())) for line in lines[1:]]
    if len(rows) != m or [r[0] for r in rows] != list(range(m)):
        raise ValueError('Incomplete per-net count file')
    return meta, [dict(transitions=r[1], unknown_changes=r[2], settled=r[3],
                       settled_unknown=r[4]) for r in rows]


def summarize(entries, timed, untimed):
    """Per-category totals; extra = timed transitions minus settled changes."""
    problems = []
    cats = defaultdict(Counter)
    for e, t, u in zip(entries, timed, untimed):
        if t['settled'] != u['settled'] or t['settled_unknown'] != u['settled_unknown']:
            problems.append(f'settled mismatch {e["driver"]}')
        extra = t['transitions'] - t['settled']
        if t['unknown_changes'] == 0 and (extra < 0 or extra % 2):
            problems.append(f'parity/negative extra {e["driver"]}')
        c = cats[e['category']]
        c['nets'] += 1
        c['timed_transitions'] += t['transitions']
        c['timed_unknown_changes'] += t['unknown_changes']
        c['settled_changes'] += t['settled']
        c['extra_transitions'] += extra
        c['nets_with_extra'] += extra > 0
        c['untimed_events'] += u['transitions']
    totals = Counter()
    for name, c in cats.items():
        if name != 'clock':
            totals.update(c)
    out = {k: dict(v) for k, v in sorted(cats.items())}
    for v in list(out.values()) + [totals]:
        v['extra_per_settled'] = (v['extra_transitions']/v['settled_changes']
                                  if v['settled_changes'] else None)
    return out, dict(totals), problems


def _run(cmd, cwd, log, timeout):
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    (cwd/log).write_text(proc.stdout + proc.stderr)
    if proc.returncode:
        raise RuntimeError(f'{cmd[0]} failed ({proc.returncode}); see {cwd/log}')
    return proc.stdout + proc.stderr


def _tool(name, sibling=None):
    path = (Path(sibling).parent/name) if sibling else shutil.which(name)
    if not path or not Path(path).is_file():
        raise RuntimeError(f'{name} not found' + (f' next to {sibling}' if sibling else ''))
    return str(Path(path).resolve())


def capture(n_images):
    if type(n_images) is not int or not 1 <= n_images <= 450:
        raise ValueError('n_images must be 1..450')
    archived = json.loads((IMPLEMENTATION/'validated_result.json').read_text())
    if (IMPLEMENTATION/'status.txt').read_text().strip() != 'validated_route_passed':
        raise ValueError('Archived implementation is not a validated passing route')
    source_hashes = {str(p): digest(p) for p in SOURCE_FILES}
    OUT_ROOT.mkdir(exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix='timed-activity.', dir=OUT_ROOT))
    report = folder/'result.json'
    result = dict(status='running', directory=str(folder), scope=__doc__.strip())
    report.write_text(json.dumps(result, indent=2)+'\n')
    try:
        for name in ('synth_uart.json', 'icebreaker_uart.pcf', 'icebreaker_uart.sdc'):
            shutil.copyfile(IMPLEMENTATION/name, folder/name)
            if digest(folder/name) != archived['input_files'][name]:
                raise ValueError(f'Archived input {name} differs from validated record')
        # Bind the routed design to the model and saved inputs.
        net = hard.load(MODEL_RUN/'model.json')
        import numpy as np
        x = np.load(MODEL_RUN/'x_test_bits.npy')
        if not np.isin(x, (0, 1)).all():
            raise ValueError('Saved inputs must be 0/1')
        params = json.loads((EXPORT/'params.json').read_text())
        rtl, _ = emit_rtl(net, pipeline=False, head_pipeline=True)
        manifest = json.loads((IMPLEMENTATION/'synth_manifest.json').read_text())
        if digest_text(rtl) != manifest['files']['dlgn_top.sv']:
            raise ValueError('Model does not regenerate the routed core RTL')
        write_vectors(net, x[:n_images], folder, params)
        for name in ('x.hex', 'exp_scores.hex', 'exp_class.hex'):
            ref = (EXPORT/name).read_text().splitlines()[:n_images]
            if (folder/name).read_text().splitlines() != ref:
                raise ValueError(f'Fresh NumPy {name} differs from export')
        tools = dict(nextpnr=_tool('nextpnr-ice40'), yosys=_tool('yosys'),
                     iverilog=_tool('iverilog'))
        tools['yosys-config'] = _tool('yosys-config', tools['yosys'])
        tools['vvp'] = _tool('vvp', tools['iverilog'])
        datdir = subprocess.check_output([tools['yosys-config'], '--datdir'], text=True).strip()
        library = Path(datdir)/'ice40/cells_sim.v'
        shutil.copyfile(library, folder/'cells_sim.v')
        log = _run([tools['nextpnr']] + NEXTPNR_ARGS, folder, 'pnr.log', 1800)
        if digest(folder/'routed_uart.asc') != archived['files']['routed_uart.asc']:
            raise ValueError('Re-route is not bit-identical to the archived bitstream')
        fmax = re.findall(r'Max frequency for clock .*?: ([0-9.]+) MHz \(PASS', log)
        if not fmax:
            raise ValueError('Re-route did not pass timing')
        routed = json.loads((folder/'routed_uart.json').read_text())
        renamed, sdf, rewritten, simple = rename_design(routed, (folder/'routed.sdf').read_text())
        (folder/'renamed.json').write_text(json.dumps(renamed)+'\n')
        (folder/'renamed.sdf').write_text(sdf)
        (folder/'cell_names.json').write_text(json.dumps(simple, indent=0)+'\n')
        _run([tools['yosys'], '-Q', '-q', '-p', 'read_json renamed.json; write_verilog -noattr renamed.v'],
             folder, 'write.log', 600)
        entries = net_ledger(renamed)
        (folder/'net-ledger.json').write_text(json.dumps(entries, indent=1)+'\n')
        (folder/'tb_timed.sv').write_text(
            testbench(entries, n_images, params, params['hardware_clks_per_bit']))
        runs = {}
        for mode, flags in (('untimed', []), ('timed', ['-gspecify', '-ginterconnect', '-DTIMING', '-DSDF'])):
            sim = f'simv_{mode}'
            _run([tools['iverilog'], '-g2012', *flags, '-o', sim, 'tb_timed.sv', 'renamed.v', 'cells_sim.v'],
                 folder, f'build_{mode}.log', 1800)
            text = _run([tools['vvp'], '-n', sim], folder, f'sim_{mode}.log', 36000)
            if f'PASS: {n_images}/{n_images} timed-netlist UART replies bit-exact' not in text:
                raise ValueError(f'{mode} simulation did not pass all replies')
            bad = [ln for ln in text.splitlines() if 'SDF' in ln and 'TIMINGCHECK not supported' not in ln]
            if bad:
                raise ValueError(f'Unexpected SDF message: {bad[0][:120]}')
            (folder/'counts.txt').rename(folder/f'counts_{mode}.txt')
            runs[mode] = parse_counts(folder/f'counts_{mode}.txt', len(entries))
        (tmeta, timed), (umeta, untimed) = runs['timed'], runs['untimed']
        if tmeta['late_events']:
            raise ValueError(f'{tmeta["late_events"]} timed events inside the pre-sample guard band')
        if tmeta['samples'] != umeta['samples']:
            raise ValueError('Timed and untimed windows differ')
        categories, totals, problems = summarize(entries, timed, untimed)
        if problems:
            raise ValueError(f'{len(problems)} consistency failures, first: {problems[0]}')
        if {str(p): digest(p) for p in SOURCE_FILES} != source_hashes:
            raise ValueError('Source changed during capture')
        result.update(
            status='passed', n_images=n_images, image_order='first N of saved test order',
            implementation=str(IMPLEMENTATION), bitstream_sha256=archived['files']['routed_uart.asc'],
            reroute_fmax_mhz=float(fmax[-1]), sdf_rewritten=rewritten,
            clock=dict(nominal_hz=12_000_000, simulated_period_ps=2*HALF_PS,
                       uart_clks_per_bit=params['hardware_clks_per_bit']),
            window=dict(rule='(first sample, last sample]; samples 1 ps before rising edges',
                        samples=tmeta['samples'], guard_ps=GUARD_PS,
                        timed_max_event_offset_ps=tmeta['max_offset_ps'],
                        untimed_max_event_offset_ps=umeta['max_offset_ps']),
            observed_net_bits=len(entries), categories=categories, totals=totals,
            semantics=['extra_transitions = timed transitions - settled changes, per net',
                       'clock nets (2 edges per sampled cycle) are reported but excluded from totals',
                       'Icarus module-path and interconnect delays are inertial; pulses narrower than a path delay are not counted',
                       'untimed_events are zero-delay simulator events (delta ordering), not glitches',
                       'settled changes agree exactly between timed and untimed runs'],
            limits=['Single nextpnr delay corner; no measured silicon glitches',
                    'Routed UART board top, not the standalone core used in 3.3-3.8',
                    'Not power or energy; no capacitance weighting',
                    f'Only the first {n_images} images in saved order'],
            tools=tools, library_sha256=digest(library), source_sha256=source_hashes,
            files_sha256={p.name: digest(p) for p in sorted(folder.iterdir())
                          if p.is_file() and p.name not in ('result.json',) and not p.name.startswith('simv')})
        report.write_text(json.dumps(result, indent=2)+'\n')
    except Exception as exc:
        result.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        report.write_text(json.dumps(result, indent=2)+'\n')
        raise
    print(f'Timed activity evidence: {report}')
    return report


def digest_text(text):
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--n', type=int, default=8, help='images from the saved order (1..450)')
    capture(ap.parse_args().n)
