"""Step 4.15: layer-targeted switching penalty, discovery then confirmation.

  python scripts/run_layer_targeting.py discover --policy docs/experiments/layer-targeting-v1.json
  python scripts/run_layer_targeting.py confirm runs/step4.15-targeting.XXXX

Trains with scripts/train.py (validation only, test deferred), measures each
model with the unchanged step 4.13 capture (270/270 RTL and zero-delay mapped
exact, core M1/M2), and applies the frozen selection and outcome rules.
Switching proxies only; no routing, glitch, power or energy result.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
import probe_mapped_switching as probe  # noqa: E402

POLICY_SCHEMA = 'layer_targeting_policy_v1'
ARCHIVE_POLICY = ROOT/'docs/experiments/hardware-switching-stop-rule-v3.json'
PROFILE_ORDER = ('L4', 'L34', 'M23', 'RAMP')
SOURCE_FILES = ('scripts/run_layer_targeting.py', 'scripts/train.py', 'dlgn/model.py',
                'dlgn/experiment.py', 'dlgn/data.py', 'dlgn/hard.py', 'dlgn/gates.py',
                'dlgn/export_verilog.py') + probe.SOURCE_FILES
TRAIN_ARGS = ['--dataset', 'digits', '--width', '1000', '--depth', '4', '--tau', '10',
              '--epochs', '60', '--bs', '100', '--lr', '0.01', '--act-mode', 'batch',
              '--split-seed', '0', '--device', 'cpu', '--defer-test']


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sources():
    return {s: digest(ROOT/s) for s in sorted(set(SOURCE_FILES))}


# ---- frozen rules (pure functions) -------------------------------------

def eligible(control_correct, correct, n):
    """Accuracy drop <= 1 percentage point, in exact integer arithmetic."""
    return (control_correct - correct)*100 <= n


def select(candidates, control_correct, n, profiles):
    """Lowest mapped M1 among eligible candidates of the given profiles.

    Ties: higher accuracy, then lower lambda, then profile order.
    """
    pool = [c for c in candidates if c['profile'] in profiles
            and eligible(control_correct, c['correct'], n)]
    if not pool:
        return None
    order = {p: i for i, p in enumerate(profiles)}
    return min(pool, key=lambda c: (c['M1'], -c['correct'], c['lambda'], order[c['profile']]))


def confirmation_outcome(rows):
    """TARGETING_BETTER only if every seed passes all three conditions."""
    ok = bool(rows) and all(r['target_eligible'] and r['R_M1_target'] >= 0.02
                            and r['R_M1_target'] > r['R_M1_comparator'] for r in rows)
    return 'TARGETING_BETTER' if ok else 'TARGETING_NOT_SHOWN'


# ---- execution ---------------------------------------------------------

def name(profile, lam):
    return f'{profile}_{str(lam).replace(".", "p")}'


def train(folder, seed, lam, weights):
    cmd = [sys.executable, str(ROOT/'scripts/train.py')] + TRAIN_ARGS + [
        '--seed', str(seed), '--act-weight', str(lam), '--out', str(folder)]
    if weights is not None:
        cmd += ['--act-layer-weights', ','.join(str(w) for w in weights)]
    env = dict(os.environ, OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=1800)
    Path(str(folder)+'.log').write_text(proc.stdout + proc.stderr)
    if proc.returncode or json.loads((folder/'status.json').read_text()).get('status') != 'passed':
        raise RuntimeError(f'Training failed: {folder}')
    return cmd


def git_state():
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'],
                                    cwd=ROOT, text=True).strip()
    if dirty:
        raise ValueError('Commit plan, policy and code before running (tracked files modified)')
    return head


def correct_count(run):
    classes = np.load(run/'validation_classes.npy')
    return int((classes == np.load(run/'y_validation.npy')).sum()), len(classes)


def measure(run, folder, window):
    summary = probe.capture_model(run, folder, {'fixed_setup': {'window': {'standalone_core': window}}})
    return summary


def build(folder, seed, lam, weights, window, label):
    run = folder/f'seed_{seed}_{label}'
    cmd = train(run, seed, lam, weights)
    probe.check_run(run, lam, seed)
    recorded = json.loads((run/'metrics.json').read_text())['args'].get('act_layer_weights')
    if recorded != (None if weights is None else [float(w) for w in weights]):
        raise ValueError(f'Recorded layer weights differ in {run}')
    correct, n = correct_count(run)
    metrics = json.loads((run/'metrics.json').read_text())
    hw = measure(run, folder/f'measure_seed_{seed}_{label}', window)
    return dict(label=label, seed=seed, **{'lambda': lam}, weights=weights, run=str(run),
                model_sha256=digest(run/'model.json'), train_command=cmd,
                correct=correct, n=n, logical_changes=metrics['validation']['changes'],
                M1=hw['metrics']['M1'], M2=hw['metrics']['M2'],
                primitive_counts=hw['primitive_counts'])


def compat(row, role):
    archive = json.loads(ARCHIVE_POLICY.read_text())['models'][f'seed_{row["seed"]}']
    if row['model_sha256'] != archive[f'{role}_model_sha256']:
        raise ValueError(f'Compatibility gate failed for seed {row["seed"]} {role}')


def load_policy(path):
    path = Path(path).resolve()
    policy = json.loads(path.read_text())
    if policy.get('schema') != POLICY_SCHEMA:
        raise ValueError('Unsupported layer-targeting policy')
    return path, policy


def relative(control, row):
    return dict(R_M1=probe.reduction(control['M1'], row['M1']),
                R_M2=probe.reduction(control['M2'], row['M2']),
                R_logical=probe.reduction(control['logical_changes'], row['logical_changes']),
                drop_pp=(control['correct']-row['correct'])*100/row['n'],
                eligible=eligible(control['correct'], row['correct'], row['n']))


def discover(policy_path, out_parent):
    policy_path, policy = load_policy(policy_path)
    folder = Path(tempfile.mkdtemp(prefix='step4.15-targeting.', dir=out_parent))
    window = probe.load_policy(ARCHIVE_POLICY)[1]['fixed_setup']['window']['standalone_core']
    plan = dict(step='4.15', phase='discovery', git_head=git_state(), policy=str(policy_path),
                policy_sha256=digest(policy_path), source_sha256=sources(),
                note='Written before any training in this folder.')
    (folder/'plan.json').write_text(json.dumps(plan, indent=2)+'\n')
    result = dict(status='running', directory=str(folder))
    report = folder/'discovery.json'
    report.write_text(json.dumps(result, indent=2)+'\n')
    try:
        seed = policy['discovery']['seed']
        control = build(folder, seed, 0, None, window, 'control')
        compat(control, 'control')
        rows = []
        for profile, weights in policy['profiles'].items():
            for lam in policy['lambdas']:
                row = build(folder, seed, lam, weights, window, name(profile, lam))
                row['profile'] = profile
                if profile == 'U' and lam == 0.3:
                    compat(row, 'penalty')
                    if (control['M1'], row['M1']) != (384982, 372638):
                        raise ValueError('Seed-1 mapped M1 does not reproduce step 4.13')
                row.update(relative(control, row))
                rows.append(row)
        t = select(rows, control['correct'], control['n'], PROFILE_ORDER)
        u = select(rows, control['correct'], control['n'], ('U',))
        if sources() != plan['source_sha256'] or digest(policy_path) != plan['policy_sha256']:
            raise ValueError('Source or policy changed during discovery')
        result.update(status='passed', seed=seed, control=control, candidates=rows,
                      T_star=t and dict(profile=t['profile'], **{'lambda': t['lambda']}),
                      U_star=u and dict(profile=u['profile'], **{'lambda': u['lambda']}),
                      outcome='SELECTED' if t else 'NO_ELIGIBLE_TARGETED')
    except Exception as exc:
        result.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        report.write_text(json.dumps(result, indent=2, default=str)+'\n')
        print(f'Discovery evidence: {report}', flush=True)


def confirm(folder):
    folder = Path(folder).resolve()
    plan = json.loads((folder/'plan.json').read_text())
    disc = json.loads((folder/'discovery.json').read_text())
    policy_path, policy = load_policy(plan['policy'])
    if disc.get('status') != 'passed' or digest(policy_path) != plan['policy_sha256'] or sources() != plan['source_sha256']:
        raise ValueError('Discovery, policy or sources do not match the plan')
    if disc['outcome'] != 'SELECTED':
        raise ValueError('No eligible targeted configuration to confirm')
    if any(json.loads(p.read_text()).get('status') == 'passed'
           for p in folder.glob('confirm.*/confirmation.json')):
        raise ValueError('A passed confirmation already exists')
    git_head = git_state()
    attempt = Path(tempfile.mkdtemp(prefix='confirm.', dir=folder))
    report = attempt/'confirmation.json'
    window = probe.load_policy(ARCHIVE_POLICY)[1]['fixed_setup']['window']['standalone_core']
    t, u = disc['T_star'], disc['U_star']
    comparator = u if u else dict(profile='U', **{'lambda': 0.3})
    result = dict(status='running', git_head=git_head, T_star=t, comparator=comparator)
    report.write_text(json.dumps(result, indent=2)+'\n')
    try:
        rows = []
        for seed in policy['confirmation']['seeds']:
            control = build(attempt, seed, 0, None, window, 'control')
            compat(control, 'control')
            built = {}
            configs = {('U', 0.3), (comparator['profile'], comparator['lambda']), (t['profile'], t['lambda'])}
            for profile, lam in sorted(configs, key=lambda c: (c[0] != 'U', c[0], c[1])):
                row = build(attempt, seed, lam, policy['profiles'][profile], window, name(profile, lam))
                row['profile'] = profile
                if profile == 'U' and lam == 0.3:
                    compat(row, 'penalty')
                row.update(relative(control, row))
                built[(profile, lam)] = row
            tr = built[(t['profile'], t['lambda'])]
            cr = built[(comparator['profile'], comparator['lambda'])]
            rows.append(dict(seed=seed, control=control, models=list(built.values()),
                             target_eligible=tr['eligible'], R_M1_target=tr['R_M1'],
                             R_M1_comparator=cr['R_M1'], drop_pp_target=tr['drop_pp'],
                             drop_pp_comparator=cr['drop_pp'],
                             conditions=dict(eligible=tr['eligible'], at_least_2pct=tr['R_M1'] >= 0.02,
                                             beats_comparator=tr['R_M1'] > cr['R_M1'])))
        if sources() != plan['source_sha256'] or digest(policy_path) != plan['policy_sha256']:
            raise ValueError('Source or policy changed during confirmation')
        mean = lambda k: float(np.mean([r[k] for r in rows]))  # noqa: E731
        result.update(status='passed', seeds=rows, outcome=confirmation_outcome(rows),
                      mean=dict(R_M1_target=mean('R_M1_target'), R_M1_comparator=mean('R_M1_comparator'),
                                drop_pp_target=mean('drop_pp_target')))
    except Exception as exc:
        result.update(status='failed', error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        report.write_text(json.dumps(result, indent=2, default=str)+'\n')
        print(f'Confirmation evidence: {report}', flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='action', required=True)
    d = sub.add_parser('discover')
    d.add_argument('--policy', required=True)
    d.add_argument('--out-parent', default=str(ROOT/'runs'))
    c = sub.add_parser('confirm')
    c.add_argument('directory')
    a = ap.parse_args()
    discover(a.policy, a.out_parent) if a.action == 'discover' else confirm(a.directory)


if __name__ == '__main__':
    main()
