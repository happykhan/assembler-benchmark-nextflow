#!/usr/bin/env python3
"""Inspect proposed real-data metadata; never download, admit or run assemblies."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchlib.real_data import inspect_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--manifest', type=Path, default=Path('assets/real-data/small-plasmids-paper.json'))
    args = parser.parse_args()
    try:
        path = args.manifest if args.manifest.is_absolute() else args.project / args.manifest
        result = inspect_manifest(json.loads(path.read_text()), args.project)
        print(json.dumps(result, indent=2, sort_keys=True))
    except (ValueError, KeyError, TypeError, OSError) as error:
        parser.exit(2, 'Real-data metadata refused: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
