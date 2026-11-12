#!/usr/bin/env python3
"""Nextflow internal setup task; users invoke nextflow run, not this script."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchlib.bootstrap import prepare_run
from benchlib.runtime import EnvironmentPreparationError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection-json', required=True)
    parser.add_argument('--runtime', choices=('pixi', 'native'), required=True)
    parser.add_argument('--runtime-image', default='')
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--existing-plan', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    args = parser.parse_args()
    try:
        plan, receipt = prepare_run(Path(__file__).resolve().parents[1], json.loads(args.selection_json),
                                    args.runtime, args.plan, args.existing_plan)
    except EnvironmentPreparationError as error:
        args.receipt.write_text(json.dumps(error.receipt, indent=2, sort_keys=True) + '\n')
        parser.exit(2, str(error) + '\n')
    except (ValueError, OSError, KeyError) as error:
        parser.exit(2, 'Run preparation refused: ' + str(error) + '\n')
    receipt['runtime_image'] = args.runtime_image or None
    args.out.write_text(json.dumps(plan, indent=2, sort_keys=True, allow_nan=False) + '\n')
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')


if __name__ == '__main__':
    main()
