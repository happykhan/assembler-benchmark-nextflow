"""Small, dependency-free sequence and provenance utilities."""
import hashlib
import json
from pathlib import Path


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.partial')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temporary.replace(path)


def fasta_lengths(path):
    lengths = []
    length = None
    with Path(path).open() as handle:
        for line in handle:
            if line.startswith('>'):
                if length is not None:
                    lengths.append(length)
                length = 0
            elif line.strip():
                if length is None:
                    raise ValueError('Sequence before FASTA header')
                length += len(line.strip())
    if length is not None:
        lengths.append(length)
    if not lengths or min(lengths) <= 0:
        raise ValueError('Reference FASTA is empty or contains an empty sequence')
    return lengths


def fastq_records(path):
    with Path(path).open() as handle:
        while True:
            name = handle.readline()
            if not name:
                return
            sequence, plus, quality = (handle.readline().rstrip('\n') for _ in range(3))
            if not name.startswith('@') or not plus.startswith('+') or not sequence or len(sequence) != len(quality):
                raise ValueError('Invalid or truncated four-line FASTQ record')
            yield name.rstrip('\n'), sequence, quality


def length_statistics(lengths):
    if not lengths:
        raise ValueError('No reads were generated')
    total = sum(lengths)
    cumulative = 0
    for length in sorted(lengths, reverse=True):
        cumulative += length
        if cumulative * 2 >= total:
            n50 = length
            break
    return {'read_count': len(lengths), 'total_bases': total,
            'min_length': min(lengths), 'max_length': max(lengths),
            'n50': n50, 'mean_length': total / len(lengths)}
