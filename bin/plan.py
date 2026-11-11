#!/usr/bin/env python3
"""List admitted cases or freeze an exact case-by-assembler run plan."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchlib.planning import build_plan, catalogue, validate_plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--preset', choices=('quick', 'standard'), default='quick')
    parser.add_argument('--groups', default='')
    parser.add_argument('--cases', default='')
    parser.add_argument('--assemblers', default='')
    parser.add_argument('--out', type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--list', action='store_true', help='Inspect choices without scheduling or downloading')
    mode.add_argument('--validate', type=Path, help='Verify an existing frozen plan against admitted sources')
    args = parser.parse_args()
    if args.list and args.out:
        parser.error('--list does not create a plan; omit --out')
    try:
        if args.validate:
            if args.groups or args.cases or args.assemblers or args.preset != 'quick':
                raise ValueError('Validation cannot change a frozen selection')
            result = validate_plan(args.project, json.loads(args.validate.read_text()))
        else:
            result = catalogue(args.project) if args.list else build_plan(args.project, args.preset, args.groups, args.cases, args.assemblers)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            try:
                with args.out.open('x') as stream:
                    stream.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n')
            except FileExistsError:
                raise ValueError('Plan already exists; refusing to overwrite a frozen selection')
        else:
            print(json.dumps(result, indent=2, sort_keys=True))
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as error:
        parser.exit(2, 'Plan refused: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
