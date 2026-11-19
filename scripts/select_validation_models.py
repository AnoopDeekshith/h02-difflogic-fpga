"""Select within a fixed validation accuracy budget; never use test metrics."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dlgn.experiment import digest, select_validation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--candidates', type=Path, nargs='+', required=True)
    parser.add_argument('--policy', type=Path, default=Path(__file__).resolve().parents[1] /
                        'docs/experiments/validation-selection-v1.json')
    parser.add_argument('--out', type=Path, required=True, help='new selection JSON file')
    args = parser.parse_args()
    policy = json.loads(args.policy.read_text())
    report = select_validation(args.control, args.candidates, policy)
    report['policy_source_sha256'] = digest(args.policy)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('x') as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(f"Selected {report['selected_directory']} using validation only")


if __name__ == '__main__':
    main()
