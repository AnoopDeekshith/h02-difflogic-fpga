"""Step 3.4: fresh diagnostic counts bound to a saved full-capture manifest.

Default totals include the whole trace (reset/fill/drain and testbench markers).
Analysis-window selection, category reporting and settled Python comparison
remain steps 3.5–3.7. This does not estimate power or demonstrate energy savings.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dlgn.vcd_activity import analyze_vcd  # noqa: E402


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def analyze_capture(capture, start_tick=None, end_tick=None):
    capture = Path(capture).resolve()
    output = Path(tempfile.mkdtemp(prefix='activity-analysis.', dir=capture))
    destination = output/'result.json'
    result = dict(status='running', directory=str(output), scope=__doc__.strip())
    destination.write_text(json.dumps(result, indent=2)+'\n')
    try:
        manifest_path = capture/'result.json'
        manifest_bytes = manifest_path.read_bytes()
        manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
        manifest = json.loads(manifest_bytes)
        if manifest.get('status') != 'passed' or 'files_sha256' not in manifest:
            raise ValueError('Expected a passed step 3.3 full-capture manifest')
        archived = manifest['files_sha256']
        required = {'dlgn.vcd', 'model.json', 'x_test_bits.npy', 'params.json',
                    'input_indices.json', 'events.csv', 'dlgn_top.sv', 'tb_activity_capture.sv'}
        if not required <= archived.keys():
            raise ValueError('Capture manifest is missing required artifact hashes')
        for name, expected in archived.items():
            if Path(name).name != name or digest(capture/name) != expected:
                raise ValueError(f'Capture artifact changed or unsafe name: {name}')
        # Bind to archived files, not mutable current training/export sources.
        # The trace is analyzed read-only; its successful capture is not a new run.
        before = digest(capture/'dlgn.vcd')
        activity = analyze_vcd(capture/'dlgn.vcd', start_tick, end_tick)
        if digest(capture/'dlgn.vcd') != before or digest(manifest_path) != manifest_hash:
            raise ValueError('Capture changed during analysis')
        # Save a separate exact copy so analysis remains bound after relocation.
        (output/'capture-manifest.json').write_bytes(manifest_bytes)
        for source in (Path(__file__).resolve(), ROOT/'dlgn/vcd_activity.py'):
            shutil.copyfile(source, output/source.name)
        result.update(status='passed', capture_directory=str(capture),
                      capture_report_sha256=manifest_hash,
                      capture_artifacts_sha256=archived,
                      source_sha256={str(p): digest(p) for p in
                                     (Path(__file__).resolve(), ROOT/'dlgn/vcd_activity.py')},
                      analysis_artifacts_sha256={name: digest(output/name) for name in
                                                 ('capture-manifest.json', 'analyze_waveform.py', 'vcd_activity.py')},
                      analysis=activity,
                      limits=['Whole-trace diagnostic unless explicit boundaries supplied',
                              'No approved useful-work window or category comparison yet',
                              'All unique VCD identifiers include testbench/control/clock',
                              'Distinct IDs with equal values are not assumed aliases',
                              'No physical glitch, power, energy or novelty claim'])
    except Exception as exc:
        result.update(status='failed', error=str(exc))
        raise
    finally:
        destination.write_text(json.dumps(result, indent=2)+'\n')
        print(f'Waveform analysis evidence: {destination}', flush=True)
    return result


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('capture', type=Path)
    ap.add_argument('--start-tick', type=int)
    ap.add_argument('--end-tick', type=int)
    args = ap.parse_args()
    analyze_capture(args.capture, args.start_tick, args.end_tick)
