"""Prepare diagnostic inputs in a Nextflow task directory with bound receipts."""
import copy
import gzip
import hashlib
from pathlib import Path
import shutil
import tempfile
import urllib.parse
import urllib.request
from .common import ROOT, digest, fasta, fingerprint, load, save, write_fasta
from .linear_cases import validate_terminal_reference
from .reads import exact_reads
from .read_order import records, record_fingerprints, permutation, write_order


def scientific_case(meta):
    case = meta.get('diagnostic_case', meta)
    if case.get('fingerprint') != fingerprint({k:v for k,v in case.items() if k != 'fingerprint'}):
        raise ValueError('Diagnostic case fingerprint mismatch')
    if not case.get('replicons') or len({r['refseq_accession'] for r in case['replicons']}) != len(case['replicons']):
        raise ValueError('Diagnostic replicon inventory is empty or duplicated')
    return case


def admit_references(case, reference_dir, offline=False):
    """Exact versioned records; pinned sequence hashes are mandatory."""
    root = Path(reference_dir)
    root.mkdir(parents=True, exist_ok=True)
    admitted = load(ROOT/'reference-admissions.json')['references']
    sequences, evidence = {}, []
    for replicon in case['replicons']:
        accession = replicon['refseq_accession']
        if not accession or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.' for c in accession):
            raise ValueError('Invalid versioned reference accession')
        expected = replicon.get('sequence_sha256') or admitted.get(accession,{}).get('sequence_sha256')
        if not expected:
            raise ValueError('No pinned diagnostic sequence admission: '+accession)
        path = root/(accession+'.fasta')
        if not path.exists():
            if offline:
                raise ValueError('Offline reference is missing: '+accession)
            url = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?'+urllib.parse.urlencode(
                {'db':'nuccore','id':accession,'rettype':'fasta','retmode':'text'})
            with urllib.request.urlopen(url,timeout=120) as response:
                content = response.read()
            # Cache entries become visible only after the same full admission.
            with tempfile.NamedTemporaryFile(prefix=accession+'.',suffix='.download',dir=root,delete=False) as temporary:
                temporary.write(content)
                downloaded=Path(temporary.name)
            try:
                check_reference(replicon, downloaded, expected)
                downloaded.replace(path)
            finally:
                downloaded.unlink(missing_ok=True)
        sequence = check_reference(replicon,path,expected)
        sequences[accession] = sequence
        evidence.append({'accession':accession,'file_sha256':digest(path),
                         'sequence_sha256':expected,'length_bp':len(sequence)})
    return sequences,evidence


def check_reference(replicon, path, expected):
    accession = replicon['refseq_accession']
    contents = fasta(path)
    if list(contents) != [accession]:
        raise ValueError('FASTA record differs from requested accession: '+accession)
    sequence = contents[accession]
    if len(sequence) != replicon['length_bp'] or not sequence or set(sequence)-set('ACGT'):
        raise ValueError('Reference length/alphabet admission failed: '+accession)
    if hashlib.sha256(sequence.encode()).hexdigest() != expected:
        raise ValueError('Pinned reference sequence checksum mismatch: '+accession)
    if replicon.get('admission_scope') in ('isolated_linear_reference_record','native_linear_genome_record'):
        validate_terminal_reference(replicon,sequence)
    return sequence


def stage_read_order(meta, case, source, output):
    """Permute full original records; duplicates, qualities and source bytes bound."""
    recipe = meta.get('input_recipe',{})
    declared, order = recipe.get('source'),recipe.get('order')
    if not declared or not order:
        raise ValueError('S7 requires a frozen source declaration and order recipe')
    source = Path(source)
    # Accept either one source case directory or the shared root/<case_id> layout.
    if not (source/'input.json').is_file():
        source=source/declared['case_id']
    if digest(source/'input.json') != declared['input_manifest_sha256']:
        raise ValueError('Frozen S7 source manifest checksum differs')
    original = load(source/'input.json')
    if original.get('status') != 'valid' or original.get('case',{}).get('id') != declared['case_id']:
        raise ValueError('S7 source is not the admitted source case')
    for name,key in [('reads.fastq.gz','reads_sha256'),('truth.fasta','truth_sha256'),('read_origins.tsv.gz','origins_sha256')]:
        if digest(source/name) != original.get(key):
            raise ValueError('Frozen S7 source checksum mismatch: '+name)
    if original['reads_sha256'] != declared['reads_sha256'] or original['truth_sha256'] != declared['truth_sha256_for_provenance_only']:
        raise ValueError('S7 source differs from frozen design')
    source_case = scientific_case(original['case'])
    if source_case['replicons'] != case['replicons'] or source_case['simulation'] != case['simulation']:
        raise ValueError('S7 source geometry or reference inventory differs')
    items = list(records(source/'reads.fastq.gz'))
    if not items:
        raise ValueError('S7 source reads are empty')
    before = record_fingerprints(items)
    indices = list(range(len(items))) if order['shuffle_seed'] is None else permutation(len(items),order['shuffle_seed'])
    if order['shuffle_seed'] is None:
        shutil.copyfile(source/'reads.fastq.gz',output/'reads.fastq.gz')
    else:
        write_order(output/'reads.fastq.gz',items,indices)
    after = record_fingerprints(records(output/'reads.fastq.gz'))
    if after['record_multiset_sha256'] != before['record_multiset_sha256'] or after['record_count'] != before['record_count']:
        raise ValueError('S7 permutation changed the read-record multiset')
    if order['shuffle_seed'] is not None and after['record_order_sha256'] == before['record_order_sha256']:
        raise ValueError('S7 shuffle failed to establish a distinct read order')
    for name in ('truth.fasta','read_origins.tsv.gz'):
        shutil.copyfile(source/name,output/name)
    return {**copy.deepcopy(original),'case':case,'reads_sha256':digest(output/'reads.fastq.gz'),
            'source_input_manifest_sha256':digest(source/'input.json'),
            'read_order':{**order,**after,'source_record_order_sha256':before['record_order_sha256'],
                          'algorithm':'read-order-sha256-sort-v1'},
            'origins_order':'Original unchanged table; associate by read identifier, never row position.'}


def prepare(meta, reference_dir, output_dir, offline=False, frozen_input_dir=None):
    case = scientific_case(meta)
    output = Path(output_dir)
    output.mkdir(parents=True,exist_ok=True)
    if any((output/name).exists() for name in ('input.json','reads.fastq.gz','truth.fasta')):
        raise ValueError('Input outputs already exist; Nextflow resume must reuse the completed task')
    if case['category'] == 'S6':
        raise ValueError('New S6 error generation is deferred; import historical evidence instead')
    if case['category'] == 'S7':
        if frozen_input_dir is None:
            raise ValueError('S7 requires --frozen-input-dir; do not simulate a substitute')
        generated = stage_read_order(meta,case,frozen_input_dir,output)
        sequences = fasta(output/'truth.fasta')
        # The truth bytes are provenance only for the S7 primary endpoint.
        reference_evidence = [{'accession':k,'sequence_sha256':hashlib.sha256(v.encode()).hexdigest(),
                               'length_bp':len(v)} for k,v in sequences.items()]
    else:
        sequences,reference_evidence = admit_references(case,reference_dir,offline)
        generated = exact_reads(case,sequences,output)
    if generated.get('status') != 'valid':
        raise ValueError('Diagnostic input failed the declared breadth/terminal admission')
    with gzip.open(output/'reads.fastq.gz','rb') as source, (output/'reads.fastq').open('wb') as target:
        shutil.copyfileobj(source,target)
    shutil.copyfile(output/'truth.fasta',output/'reference.fasta')
    reference = {'schema_version':1,'status':'admitted','track':'diagnostic','mode':'diagnostic_replicons',
                 'reference_id':meta.get('reference_id'), 'reference_sha256':digest(output/'truth.fasta'),
                 'molecule_types':{r['refseq_accession']:r['molecule_type'] for r in case['replicons']},
                 'replicons':case['replicons'],'reference_admission':reference_evidence,
                 'headline_eligible':False}
    save(output/'reference.json',reference)
    result = {**generated,'legacy_status':generated['status'],'status':'completed',
              'case':meta,'diagnostic_case':case,'track':'diagnostic',
              'reads_gzip_sha256':generated['reads_sha256'],'reads_sha256':digest(output/'reads.fastq'),
              'reference_sha256':digest(output/'truth.fasta'),
              'reference_provenance_sha256':digest(output/'reference.json'),
              'generator_source_sha256':digest(Path(__file__))}
    save(output/'input.json',result)
    return result
