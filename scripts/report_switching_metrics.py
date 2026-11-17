"""Step 3.10: complementary switching metrics for the historical digits baseline.

Puts side by side, with explicit populations and denominators:

1. the training surrogate 2p(1-p) (p = mean hard output over the saved images)
2. settled logical changes in the saved order, overall and per layer
3. the finite-sample random-order expectation 2m(n-m)/(n(n-1)) and an
   empirical permutation check
4. tracked RTL waveform categories (3.6), mapped net bits (3.8) and the
   SDF-timed glitch estimate on the routed board (3.9)

These views use different populations, windows and workloads. They are
complementary, not independent evidence of energy savings.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dlgn import hard  # noqa: E402

RESULTS = ROOT/'docs/results'
TRACKED = {'3.6': 'step-3.6-activity-categories.json', '3.7': 'step-3.7-numpy-rtl-activity.json',
           '3.8': 'step-3.8-mapped-activity.json', '3.9': 'step-3.9-timed-activity.json'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def adjacent_changes(h):
    return int((h[1:] != h[:-1]).sum())


def layer_view(h, permutations, rng):
    """Surrogate, saved-order and random-order switching for one bit matrix."""
    n, width = h.shape
    p = h.mean(0)
    ones = h.sum(0)
    pairs = (n - 1) * width
    saved = adjacent_changes(h)
    exact = float((2*ones*(n - ones)).sum() / (n*(n - 1)) / width)
    rates = np.array([adjacent_changes(h[rng.permutation(n)]) / pairs for _ in range(permutations)])
    return dict(
        width=width, images=n, adjacent_pairs=n - 1, bit_pair_opportunities=pairs,
        surrogate_mean_2p1mp=float((2*p*(1 - p)).mean()),
        saved_order_changes=saved, saved_order_rate=saved/pairs,
        random_order_expected_rate=exact,
        random_order_empirical=dict(permutations=permutations, mean=float(rates.mean()),
                                    std=float(rates.std()), min=float(rates.min()),
                                    max=float(rates.max())),
        constant_bits=int(((p == 0) | (p == 1)).sum()))


def report(model_run, permutations=200, seed=0, results=RESULTS):
    model_run = Path(model_run)
    net = hard.load(model_run/'model.json')
    x = np.load(model_run/'x_test_bits.npy')
    if x.ndim != 2 or len(x) < 2 or not np.isin(x, (0, 1)).all():
        raise ValueError('Expected at least two ordered 0/1 input vectors')
    x = x.astype(bool)
    rng = np.random.default_rng(seed)
    outs = hard.forward_bits(net, x)
    layers = {f'l{i+1}': layer_view(h, permutations, rng) for i, h in enumerate(outs)}
    all_gates = layer_view(np.concatenate(outs, axis=1), permutations, rng)
    inputs = layer_view(x, permutations, rng)
    toggle = hard.toggle_rate(net, x)
    if not np.isclose(toggle, all_gates['saved_order_rate'], rtol=0, atol=1e-15):
        raise ValueError('hard.toggle_rate disagrees with the layer computation')
    for view in list(layers.values()) + [all_gates, inputs]:
        if abs(view['random_order_empirical']['mean'] - view['random_order_expected_rate']) > \
                5*view['random_order_empirical']['std']/np.sqrt(permutations) + 1e-12:
            raise ValueError('Permutation mean departs from the exact random-order expectation')

    tracked, hashes = {}, {}
    for step, name in TRACKED.items():
        path = Path(results)/name
        tracked[step] = json.loads(path.read_text())
        hashes[name] = sha(path)
    r37 = tracked['3.7']
    rtl_layers = {o['signal']: o['rtl']['known_bit_toggles'] for o in r37['observations']
                  if o.get('canonical_logical_output')}
    numpy_layers = {f'{k}_c': v['saved_order_changes'] for k, v in layers.items()}
    if rtl_layers != numpy_layers:
        raise ValueError(f'Saved-order layer changes differ from 3.7 RTL: {rtl_layers} vs {numpy_layers}')
    if r37['logical_gate_output_metric']['known_bit_toggles'] != all_gates['saved_order_changes']:
        raise ValueError('Total logical changes differ from 3.7')
    x_obs = next(o for o in r37['observations'] if o['signal'] == 'x')
    if x_obs['rtl']['known_bit_toggles'] != inputs['saved_order_changes']:
        raise ValueError('Input-port changes differ from 3.7')

    whole = tracked['3.6']['whole_trace']['categories']
    rtl_categories = {k: v['counts']['known_bit_toggles'] for k, v in whole.items()}
    mapped = tracked['3.8']['activity']
    timed = tracked['3.9']
    table = [
        dict(metric='Training surrogate mean 2p(1-p)', population='4,000 learned gates (hard outputs)',
             denominator='per gate; order-free', value=all_gates['surrogate_mean_2p1mp'], source='this step'),
        dict(metric='Random-order expected change rate', population='4,000 learned gates',
             denominator='per gate per image pair (finite-sample exact)',
             value=all_gates['random_order_expected_rate'], source='this step'),
        dict(metric='Saved-order settled change rate', population='4,000 learned gates',
             denominator=f'{all_gates["bit_pair_opportunities"]:,} gate-pair opportunities',
             value=all_gates['saved_order_rate'], source='3.7 (RTL = NumPy)'),
        dict(metric='Saved-order input-bit change rate', population='192 thermometer input bits',
             denominator=f'{inputs["bit_pair_opportunities"]:,} bit-pair opportunities',
             value=inputs['saved_order_rate'], source='3.7'),
        dict(metric='RTL whole-trace known flips', population='1,036 VCD identifiers, all categories',
             denominator='count; includes reset/fill/drain, copies, clock', value=sum(rtl_categories.values()),
             source='3.6'),
        dict(metric='Mapped whole-trace known flips', population='3,569 unique iCE40UP net bits (zero delay)',
             denominator='count; standalone core, 450 images',
             value=mapped['whole_trace']['totals']['known_toggles'], source='3.8'),
        dict(metric='Timed extra per settled change, core',
             population=f'{timed["categories"]["core"]["nets"]:,} routed core net bits',
             denominator=f'per settled change; {timed["n_images"]} images, SDF delays',
             value=timed['categories']['core']['extra_per_settled'], source='3.9'),
        dict(metric='Timed extra per settled change, all non-clock',
             population=f'{timed["totals"]["nets"]:,} routed UART-board non-clock net bits',
             denominator='per settled change; dominated by UART interface nets',
             value=timed['totals']['extra_per_settled'], source='3.9'),
    ]
    return dict(
        step='3.10', scope=__doc__.strip(), model_run=str(model_run),
        model_sha256=sha(model_run/'model.json'), inputs_sha256=sha(model_run/'x_test_bits.npy'),
        order='saved test order (450 images) unless stated', permutation_seed=seed,
        logical=dict(layers=layers, all_gates=all_gates, input_bits=inputs),
        rtl_whole_trace_categories=rtl_categories,
        mapped_categories={w: mapped[w]['categories'] for w in ('whole_trace', 'complete_burst')},
        timed=dict(categories=timed['categories'], totals=timed['totals'], n_images=timed['n_images']),
        table=table, tracked_results_sha256=hashes,
        interpretation=[
            '2p(1-p) assumes independent consecutive inputs; it ignores order',
            'For a random order of a fixed image set the exact expectation is 2m(n-m)/(n(n-1))',
            'Saved-order rate exceeds it by under one permutation standard deviation (within shuffle noise)',
            'Timed core nets include popcount/score/argmax logic, a wider population than the 4,000 gates',
            'RTL/mapped/timed counts use different populations, windows and workloads; do not subtract them',
            'No metric here is power or energy'],
        limits=['Historical exploratory baseline (test data already inspected), not a matched control',
                'Surrogate uses hard outputs on the test set; training uses soft outputs on train batches',
                'Timed glitch estimate covers only the first images on the routed UART board'])


if __name__ == '__main__':
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('model_run', type=Path, nargs='?', default=ROOT/'runs/digits_w1000')
    ap.add_argument('--out', type=Path, default=RESULTS/'step-3.10-switching-metrics.json')
    ap.add_argument('--permutations', type=int, default=200)
    a = ap.parse_args()
    out = report(a.model_run, a.permutations)
    a.out.write_text(json.dumps(out, indent=2)+'\n')
    for row in out['table']:
        print(f"{row['metric']:<46} {row['value']:>14,.6g}  [{row['source']}]")
