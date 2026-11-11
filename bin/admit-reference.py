#!/usr/bin/env python3
"""Verify an explicitly admitted whole reference without altering its registry."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchlib.references import prepare_reference, sha256_bytes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', type=Path, required=True)
    parser.add_argument('--id', required=True)
    parser.add_argument('--reference-dir', type=Path, required=True)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('Admission check receipt already exists; refusing to overwrite')
    try:
        raw_registry = args.registry.read_bytes()
        fasta, metadata = prepare_reference(json.loads(raw_registry), args.id, args.reference_dir, args.offline)
        if metadata.get('mode') != 'whole_genome':
            raise ValueError('A Quick fragment is not a whole-genome admission')
        receipt = {'schema_version': 1, 'status': 'verified_simulation_reference',
                   'reference_id': args.id, 'registry_sha256': sha256_bytes(raw_registry),
                   'source_sha256': metadata['download_sha256'],
                   'canonical_fasta_sha256': sha256_bytes(fasta), 'molecules': metadata['molecules'],
                   'truth_scope': metadata['truth_scope']}
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open('x') as stream:
            json.dump(receipt, stream, indent=2, sort_keys=True)
            stream.write('\n')
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as error:
        parser.exit(2, 'Reference admission check refused: ' + str(error) + '\n')


if __name__ == '__main__':
    main()
