#!/usr/bin/env python3
"""Prepare the exact same checksummed reference online or from a prefilled cache."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchlib.references import prepare_reference


def prepare(registry, reference_id, cache, offline=False):
    return prepare_reference(registry, reference_id, cache, offline)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--registry', type=Path, required=True)
    p.add_argument('--id', required=True)
    p.add_argument('--reference-dir', type=Path, required=True)
    p.add_argument('--offline', action='store_true')
    p.add_argument('--out', type=Path, default=Path('reference.fasta'))
    p.add_argument('--metadata', type=Path, default=Path('reference.json'))
    a = p.parse_args()
    fasta, metadata = prepare(json.loads(a.registry.read_text()), a.id, a.reference_dir, a.offline)
    a.out.write_bytes(fasta)
    a.metadata.write_text(json.dumps(metadata, indent=2) + '\n')


if __name__ == '__main__':
    main()
