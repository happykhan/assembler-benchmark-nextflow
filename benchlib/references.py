"""Checked source preparation with explicit native-molecule inventories."""
import gzip
import hashlib
import re

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
