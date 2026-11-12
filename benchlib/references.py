"""Checked source preparation with explicit native-molecule inventories."""
import fcntl
import gzip
import hashlib
from pathlib import Path
import re
import tempfile
import urllib.request

SAFE_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]*\Z')
ACCESSION = re.compile(r'[A-Z][A-Z0-9_]*\.[0-9]+\Z')
HEX_SHA256 = re.compile(r'[0-9a-f]{64}\Z')
IUPAC_DNA = set('ACGTRYSWKMBDHVN')


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def read_fasta(text):
    """Reject duplicate names, empty records and malformed source sequence."""
    records, current = {}, None
    for line in text.splitlines():
        if not line.strip():
            continue
        if line.startswith('>'):
            parts = line[1:].split()
            if not parts or parts[0] in records:
                raise ValueError('Missing or duplicate source FASTA accession')
            current = parts[0]
            records[current] = []
        else:
            sequence = line.strip().upper()
            if current is None:
                raise ValueError('Sequence precedes source FASTA accession')
            if not set(sequence) <= IUPAC_DNA:
                raise ValueError('Source FASTA has invalid DNA symbols')
            records[current].append(sequence)
    joined = {name: ''.join(parts) for name, parts in records.items()}
    if not joined or any(not sequence for sequence in joined.values()):
        raise ValueError('Source FASTA is empty or has an empty molecule')
    return joined


def source_records(data, compression='gzip'):
    if compression == 'gzip':
        data = gzip.decompress(data)
    elif compression != 'none':
        raise ValueError('Unsupported reference source compression')
    records = read_fasta(data.decode('ascii'))
    # ENA FASTA uses ENA|accession|accession.version as its first field.
    normalised = {}
    for name, sequence in records.items():
        accession = name.split('|')[-1] if name.startswith('ENA|') else name
        if accession in normalised:
            raise ValueError('Duplicate source accession after FASTA header normalisation')
        normalised[accession] = sequence
    return normalised


def sequence_statistics(sequence):
    gc = sequence.count('G') + sequence.count('C')
    ambiguous = sum(base not in 'ACGT' for base in sequence)
    return {'length_bp': len(sequence), 'sequence_sha256': sha256_bytes(sequence.encode('ascii')),
            'gc_bases': gc, 'gc_fraction': gc / len(sequence), 'ambiguous_bases': ambiguous}


def validate_reference_definition(row):
    """Validate declared evidence before source bytes are downloaded or used."""
    if row.get('preparation') != 'whole_genome' or row.get('status') != 'admitted':
        raise ValueError('Whole reference must be explicitly admitted')
    if 'quick_slice_bases' in row:
        raise ValueError('Whole reference must not specify slicing')
    for field in ('download_sha256', 'canonical_fasta_sha256'):
        if not isinstance(row.get(field), str) or not HEX_SHA256.fullmatch(row[field]):
            raise ValueError('Whole reference requires ' + field)
    molecules = row.get('molecules')
    if not isinstance(molecules, list) or not molecules:
        raise ValueError('Whole reference requires an explicit molecule inventory')
    seen = set()
    for molecule in molecules:
        accession = molecule.get('accession')
        if not isinstance(accession, str) or not ACCESSION.fullmatch(accession) or accession in seen:
            raise ValueError('Molecule accessions must be unique and versioned')
        seen.add(accession)
        if molecule.get('type') not in ('chromosome', 'plasmid'):
            raise ValueError('Molecule type requires explicit evidence')
        if molecule.get('topology') not in ('linear', 'circular'):
            raise ValueError('Molecule topology requires explicit evidence')
        length = molecule.get('length_bp')
        if type(length) is not int or length < 1:
            raise ValueError('Molecule length must be positive')
        for field in ('gc_bases', 'ambiguous_bases'):
            value = molecule.get(field)
            if type(value) is not int or not 0 <= value <= length:
                raise ValueError('Invalid molecule ' + field)
        checksum = molecule.get('sequence_sha256')
        if not isinstance(checksum, str) or not HEX_SHA256.fullmatch(checksum):
            raise ValueError('Molecule sequence SHA256 is required')
    return row


def validate_molecules(records, molecules):
    """Bind source sequences to declared inventory without inferring topology."""
    if not isinstance(molecules, list) or not molecules:
        raise ValueError('Whole reference requires an explicit molecule inventory')
    names, measured = [], []
    for molecule in molecules:
        accession = molecule['accession']
        if accession in names or accession not in records:
            raise ValueError('Declared molecule missing or duplicated: ' + accession)
        names.append(accession)
        stats = sequence_statistics(records[accession])
        for key in ('length_bp', 'sequence_sha256', 'gc_bases', 'ambiguous_bases'):
            if molecule.get(key) != stats[key]:
                raise ValueError('Molecule ' + key + ' mismatch: ' + accession)
        measured.append(dict(molecule, **stats))
    if set(records) != set(names):
        raise ValueError('Source molecule inventory contains undeclared extra records')
    return measured


def canonical_fasta(records, molecules):
    """Keep native molecule names and declare circularity for the simulator."""
    validate_molecules(records, molecules)
    parts = []
    for molecule in molecules:
        accession = molecule['accession']
        circular = 'true' if molecule['topology'] == 'circular' else 'false'
        sequence = records[accession]
        parts.append(f'>{accession} circular={circular}\n')
        parts.extend(sequence[i:i + 80] + '\n' for i in range(0, len(sequence), 80))
    return ''.join(parts).encode('ascii')


def cached_source(row, cache, offline):
    reference_id, checksum = row.get('id'), row.get('download_sha256')
    if not isinstance(reference_id, str) or not SAFE_ID.fullmatch(reference_id):
        raise ValueError('Unsafe reference ID')
    if not isinstance(checksum, str) or not HEX_SHA256.fullmatch(checksum):
        raise ValueError('Reference source requires a SHA256 checksum')
    cache = Path(cache)
    cache.mkdir(parents=True, exist_ok=True)
    source = cache / (reference_id + '.source.gz')
    with (cache / ('.' + reference_id + '.lock')).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not source.exists():
            if offline:
                raise ValueError('Offline reference missing: ' + str(source))
            with tempfile.NamedTemporaryFile(dir=cache, delete=False) as handle:
                temporary = Path(handle.name)
                try:
                    sources = row.get('sources') or [{'url': row['url']}]
                    for component in sources:
                        with urllib.request.urlopen(component['url'], timeout=90) as response:
                            payload = response.read()
                        if component.get('sha256') and sha256_bytes(payload) != component['sha256']:
                            raise ValueError('Reference component checksum mismatch')
                        handle.write(payload)
                    handle.flush()
                    if sha256_bytes(temporary.read_bytes()) != checksum:
                        raise ValueError('Downloaded reference checksum mismatch')
                    temporary.replace(source)
                finally:
                    temporary.unlink(missing_ok=True)
        data = source.read_bytes()
        if sha256_bytes(data) != checksum:
            raise ValueError('Cached reference checksum mismatch')
    return data


def prepare_reference(registry, reference_id, cache, offline=False):
    rows = [row for row in registry['references'] if row['id'] == reference_id]
    if len(rows) != 1:
        raise ValueError('Unknown or duplicate reference ID')
    row = rows[0]
    if row.get('preparation') == 'whole_genome':
        validate_reference_definition(row)
    data = cached_source(row, cache, offline)
    records = source_records(data, row.get('compression', 'gzip'))
    if row.get('preparation') == 'whole_genome':
        molecules = validate_molecules(records, row['molecules'])
        fasta = canonical_fasta(records, molecules)
        expected = row['canonical_fasta_sha256']
        if sha256_bytes(fasta) != expected:
            raise ValueError('Whole canonical FASTA checksum mismatch')
        provenance = dict(row, reference_sha256=expected, source_sha256=sha256_bytes(data),
                          mode='whole_genome', molecule_types={m['accession']: m['type'] for m in molecules},
                          molecules=molecules, total_length_bp=sum(m['length_bp'] for m in molecules),
                          headline_eligible=False,
                          truth_scope=row.get('truth_scope', 'Frozen published sequence used as simulation truth; not validated truth for real-isolate reads'))
        return fasta, provenance
    # Preserve the original Quick fixture's exact header, sequence and wrapping.
    if len(records) != 1 or not set(next(iter(records.values()))) <= set('ACGT'):
        raise ValueError('Initial Quick reference requires one unambiguous chromosome')
    original_molecule, original_sequence = next(iter(records.items()))
    length = row.get('quick_slice_bases')
    if type(length) is not int or not 0 < length <= len(original_sequence):
        raise ValueError('Quick slice exceeds the verified source sequence')
    sequence = original_sequence[:length]
    fasta = ('>' + reference_id + ' workflow_fixture linear=true\n' +
             '\n'.join(sequence[i:i + 80] for i in range(0, len(sequence), 80)) + '\n').encode('ascii')
    provenance = dict(row, reference_sha256=sha256_bytes(fasta), original_length=len(original_sequence),
                      fixture_length=len(sequence), original_molecule=original_molecule,
                      interval_zero_based=[0, len(sequence)], topology='linear', headline_eligible=False)
    return fasta, provenance
