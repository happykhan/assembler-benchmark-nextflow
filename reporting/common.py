"""Small file and provenance helpers shared by the benchmark stages."""
import gzip
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def load(path):
    return json.loads(Path(path).read_text())

def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')
    temp.replace(path)

def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()

def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

def fasta(path):
    records = {}
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt') as stream:
        name = None
        chunks = []
        for line in stream:
            line = line.strip()
            if not line:
                continue
            if line.startswith('>'):
                if name is not None:
                    records[name] = ''.join(chunks).upper()
                name = line[1:].split()[0]
                if not name or name in records:
                    raise ValueError(f'Missing or duplicate FASTA identifier in {path}')
                chunks = []
            elif name is None:
                raise ValueError(f'Sequence before FASTA header in {path}')
            else:
                chunks.append(line)
        if name is not None:
            if name in records:
                raise ValueError(f'Duplicate FASTA identifier {name}')
            records[name] = ''.join(chunks).upper()
    return records

def write_fasta(path, records):
    with Path(path).open('w') as stream:
        for name, sequence in records.items():
            stream.write(f'>{name}\n')
            for start in range(0, len(sequence), 80):
                stream.write(sequence[start:start + 80] + '\n')

def reverse_complement(sequence):
    return sequence.translate(str.maketrans('ACGT', 'TGCA'))[::-1]

def within_root(path):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError(f'Output must stay within {ROOT}')
    return path
