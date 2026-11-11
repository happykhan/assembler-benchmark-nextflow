#!/usr/bin/env python3
"""Prepare a frozen plan's locked environments before running on compute nodes."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchlib.runtime import EnvironmentPreparationError, prepare_environments


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--pixi', default='pixi')
    parser.add_argument('--out', type=Path, help='Optional JSON receipt, including any failed preparation')
    args = parser.parse_args()
    try:
        plan = json.loads(args.plan.read_text())
        receipt = prepare_environments(Path(__file__).resolve().parents[1], plan, args.pixi)
        code = 0
    except EnvironmentPreparationError as error:
        receipt, code = error.receipt, 2
    except (ValueError, OSError, json.JSONDecodeError) as error:
        parser.exit(2, f'Environment preparation refused: {error}\n')
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return code


if __name__ == '__main__':
    sys.exit(main())
