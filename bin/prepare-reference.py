#!/usr/bin/env python3
"""Prepare the exact same checksummed reference online or from a prefilled cache."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile
import urllib.request


def prepare(registry, reference_id, cache, offline=False):
    rows = [r for r in registry['references'] if r['id'] == reference_id]
    if len(rows) != 1:
        raise ValueError('Unknown or duplicate reference ID')
    row = rows[0]
    cache.mkdir(parents=True, exist_ok=True)
    source = cache / (reference_id + '.source.gz')
    if not source.exists():
        if offline:
            raise ValueError('Offline reference missing: ' + str(source))
        with tempfile.NamedTemporaryFile(dir=cache, delete=False) as handle:
            temporary = Path(handle.name)
            try:
                with urllib.request.urlopen(row['url'], timeout=60) as response:
                    while chunk := response.read(1024 * 1024):
                        handle.write(chunk)
                handle.flush()
                if hashlib.sha256(temporary.read_bytes()).hexdigest() != row['download_sha256']:
                    raise ValueError('Downloaded reference checksum mismatch')
                os.replace(temporary, source)
            finally:
                temporary.unlink(missing_ok=True)
    if hashlib.sha256(source.read_bytes()).hexdigest() != row['download_sha256']:
        raise ValueError('Cached reference checksum mismatch')
    text = gzip.decompress(source.read_bytes()).decode('ascii')
    records = []
    for line in text.splitlines():
        if line.startswith('>'):
            records.append([line[1:].split()[0], ''])
        elif line.strip():
            records[-1][1] += line.strip().upper()
    if len(records) != 1 or not set(records[0][1]) <= set('ACGT'):
        raise ValueError('Initial Quick reference requires one unambiguous chromosome')
    sequence = records[0][1][:row['quick_slice_bases']]
    fasta = ('>' + reference_id + ' workflow_fixture linear=true\n' +
             '\n'.join(sequence[i:i+80] for i in range(0, len(sequence), 80)) + '\n').encode()
    provenance = dict(row, reference_sha256=hashlib.sha256(fasta).hexdigest(),
                      original_length=len(records[0][1]), fixture_length=len(sequence),
                      original_molecule=records[0][0], interval_zero_based=[0, len(sequence)],
                      topology='linear', headline_eligible=False)
    return fasta, provenance


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
