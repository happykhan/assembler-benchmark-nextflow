#!/usr/bin/env python3
"""Read-only exact-sequence audit of realised Standard simulation inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import re

HEADER = re.compile(rb'(?:^|\s)([A-Z0-9_.]+),([+-])strand,(\d+)-(\d+)(?:\s|$)')
RC = bytes.maketrans(b'ACGT', b'TGCA')


def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def reference_sequences(path):
    rows = {}
    current = None
    with path.open('rb') as handle:
        for line in handle:
            if line.startswith(b'>'):
                current = line[1:].split()[0]
                if current in rows or b'circular=true' not in line.split():
                    raise ValueError('Reference inventory or circular topology mismatch')
                rows[current] = []
            elif line.strip():
                if current is None:
                    raise ValueError('Sequence precedes reference header')
                rows[current].append(line.strip().upper())
    return {key: b''.join(parts) for key, parts in rows.items()}


def audit(directory):
    simulation = json.loads((directory / 'simulation.json').read_text())
    reference = directory / 'reference.fasta'
    references = reference_sequences(reference)
    doubled = {}
    for name, sequence in references.items():
        if not set(sequence) <= set(b'ACGT'):
            raise ValueError('Reference contains unsupported symbols')
        doubled[(name, b'+')] = sequence * 2
        doubled[(name, b'-')] = sequence.translate(RC)[::-1] * 2
    result = {'case_id': simulation['case']['id'], 'directory': str(directory),
              'reads_sha256': None, 'reference_sha256': sha(reference),
              'read_count': 0, 'total_bases': 0, 'exact_reference_prefix_reads': 0,
              'nonidentical_reads': 0, 'nonidentical_positions': 0,
              'trimmed_budget_reads': 0, 'circular_wrap_reads': 0,
              'plus_strand_reads': 0, 'minus_strand_reads': 0, 'examples': []}
    digest = hashlib.sha256()
    with (directory / 'reads.fastq').open('rb') as handle:
        while True:
            header = handle.readline()
            if not header:
                break
            sequence, separator, qualities = (handle.readline() for _ in range(3))
            for line in (header, sequence, separator, qualities):
                digest.update(line)
            sequence, qualities = sequence.rstrip(b'\r\n'), qualities.rstrip(b'\r\n')
            if not header.startswith(b'@') or not separator.startswith(b'+') or not sequence or len(sequence) != len(qualities):
                raise ValueError('Malformed FASTQ record')
            match = HEADER.search(header)
            if not match:
                raise ValueError('Missing source-coordinate header')
            name, strand, start, end = match.groups()
            start, end = int(start), int(end)
            genome_length = len(references[name])
            if not 0 <= start < genome_length or not start < end <= start + genome_length:
                raise ValueError('Source coordinates outside circular fragment bounds')
            if len(sequence) > end - start:
                raise ValueError('Read exceeds declared source fragment')
            expected = doubled[(name, strand)][start:start + len(sequence)]
            differences = sum(a != b for a, b in zip(sequence, expected)) + abs(len(sequence) - len(expected))
            result['read_count'] += 1
            result['total_bases'] += len(sequence)
            result['plus_strand_reads' if strand == b'+' else 'minus_strand_reads'] += 1
            result['circular_wrap_reads'] += start + len(sequence) > genome_length
            result['trimmed_budget_reads'] += len(sequence) < end - start
            if differences:
                result['nonidentical_reads'] += 1
                result['nonidentical_positions'] += differences
                if len(result['examples']) < 5:
                    result['examples'].append({'header': header.decode().strip(), 'nonidentical_positions': differences})
            else:
                result['exact_reference_prefix_reads'] += 1
    result['reads_sha256'] = digest.hexdigest()
    result['reads_hash_matches_simulation'] = result['reads_sha256'] == simulation['reads_sha256']
    result['reference_hash_matches_simulation'] = result['reference_sha256'] == simulation['reference_sha256']
    result['read_count_matches_simulation'] = result['read_count'] == simulation['observed']['read_count']
    result['base_budget_matches_simulation'] = result['total_bases'] == simulation['target_bases'] == simulation['observed']['total_bases']
    result['coverage'] = result['total_bases'] / sum(map(len, references.values()))
    result['verified_error_free'] = (result['nonidentical_reads'] == 0
        and all(result[key] for key in ('reads_hash_matches_simulation', 'reference_hash_matches_simulation',
                                       'read_count_matches_simulation', 'base_budget_matches_simulation')))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    directories = []
    for pattern in ('df/d3e3ba*', '8d/dac1d9*'):
        found = list((args.root / 'work/standard-baseline-v1').glob(pattern))
        if len(found) != 1:
            raise ValueError('Expected one frozen simulation directory for ' + pattern)
        directories.extend(found)
    results = [audit(path) for path in directories]
    output = {'schema_version': 1, 'status': 'verified' if all(r['verified_error_free'] for r in results) else 'needs_review',
              'method': 'Every realised read compared byte-for-byte with the prefix of its declared Badread source fragment, using strand-specific circular reference coordinates; budget-trimmed final reads handled explicitly.',
              'limitations': ['Coordinate and strand conventions are those of installed Badread0.4.2; mismatch positions are direct comparison, not inferred edit-operation counts.',
                              'This audit verifies input sequences, not the cause of any assembly outcome.'],
              'results': results}
    with args.out.open('x') as handle:
        json.dump(output, handle, indent=2, sort_keys=True)
        handle.write('\n')
    print(json.dumps(output, indent=2))
    raise SystemExit(0 if output['status'] == 'verified' else 2)


if __name__ == '__main__':
    main()
