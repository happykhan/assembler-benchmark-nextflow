from pathlib import Path
import copy
import csv
import re
import tempfile
import shlex
from .common import ROOT, digest, load, save
from .identities import result_slug as result_id
VERSION = 1
IDENTIFIER = re.compile('[A-Za-z0-9][A-Za-z0-9_.-]*\\Z')

def identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError('Bundle identifiers must be simple names')
    return value

def checked_document(document):
    if not isinstance(document, dict) or document.get('schema_version') != 1:
        raise ValueError('Unsupported source snapshot schema')
    identifier(document['batch'])
    cases = {identifier(case['id']): case for case in document['scenarios']}
    if len(cases) != len(document['scenarios']):
        raise ValueError('Duplicate scenario identity')
    seen = set()
    for record in document['results']:
        key = result_id(record)
        if key in seen or record['scenario_id'] not in cases:
            raise ValueError('Duplicate execution or unknown scenario')
        seen.add(key)
        review = record.get('sequence_review') or {}
        if review.get('status') == 'verified':
            hashes = review.get('hashes') or {}
            if review.get('scenario_id') != record['scenario_id'] or review.get('tool') != record['tool'] or any((not record.get(name) or hashes.get(name) != record[name] for name in ('assembly_sha256', 'truth_sha256'))):
                raise ValueError('Verified review provenance differs from the execution')
        artifact = record.get('graph_artifacts') or {}
        attached = artifact.get('input_hashes', {}).get('assembly_sha256')
        if attached and record.get('assembly_sha256') and (attached != record['assembly_sha256']):
            raise ValueError('Graph assembly hash differs from scored assembly')
    return document

def load_bundle(path):
    """Validate the complete bundle before a renderer writes any output."""
    path = Path(path)
    manifest = load(path / 'manifest.json')
    if not isinstance(manifest, dict) or manifest.get('kind') != 'ploptimizer-results-bundle' or manifest.get('schema_version') != VERSION:
        raise ValueError('Unsupported results bundle')
    if not {'primary_batch', 'batches', 'sources', 'cohort', 'producer', 'files'} <= set(manifest):
        raise ValueError('Bundle manifest is incomplete')
    if not isinstance(manifest.get('files'), dict) or not manifest['files'] or (not isinstance(manifest.get('batches'), list)) or (not manifest['batches']):
        raise ValueError('Bundle manifest is incomplete')
    for batch in manifest['batches']:
        identifier(batch)
    required = {'README.md', 'summary.tsv', 'molecules.tsv', 'overview.json'}
    for batch in manifest['batches']:
        required.update({f'batches/{batch}.json', f'models/{batch}.json'})
    if not required <= set(manifest['files']):
        raise ValueError('Bundle manifest omits required files')
    for name, expected in manifest['files'].items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or (path / relative).is_symlink() or (not (path / relative).is_file()) or (digest(path / relative) != expected):
            raise ValueError(f'Bundle file failed integrity validation: {name}')
    expected_files = set(manifest['files']) | {'manifest.json'}
    if {str(p.relative_to(path)) for p in path.rglob('*') if p.is_file()} != expected_files:
        raise ValueError('Bundle contains unmanifested files')
    documents = [checked_document(load(path / 'batches' / f'{identifier(batch)}.json')) for batch in manifest['batches']]
    if manifest['primary_batch'] not in manifest['batches'] or len(set(manifest['batches'])) != len(manifest['batches']):
        raise ValueError('Invalid bundle batch identities')
    for batch, document in zip(manifest['batches'], documents):
        if document['batch'] != batch:
            raise ValueError('Bundle document batch identity mismatch')
        if document.get('report_bundle_version') != VERSION or any((r.get('report_evidence', {}).get('schema_version') != VERSION for r in document['results'])):
            raise ValueError('Bundle lacks prepared report evidence')
        for record in document['results']:
            slug = result_id(record)
            required = {f'reports/{batch}/{slug}.json', f'reports/{batch}/{slug}.md'}
            if record['report_evidence']['dotplot']['status'] == 'available':
                required.update({f'reports/{batch}/{slug}-alignment.svg', f'reports/{batch}/{slug}-alignments.tsv'})
                if record['report_evidence']['dotplot'].get('nucmer_status') == 'available':
                    required.add(f'reports/{batch}/{slug}-original-show-coords.tsv')
            if not required <= set(manifest['files']):
                raise ValueError('Bundle omits a result report or plot')
    return (manifest, documents)
