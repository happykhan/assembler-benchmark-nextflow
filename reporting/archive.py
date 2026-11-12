"""Lossless admission and presentation dispatch for sealed result bundles.

A historical bundle and a native Nextflow bundle are two versioned producers of
this archive contract. Admission never changes their records or file inventory.
"""
import json
from pathlib import Path
import re
import shutil
import tempfile

from .common import digest, load, save

SHA256 = re.compile(r'[a-f0-9]{64}\Z')


def validate_archive(source):
    source = Path(source).resolve()
    manifest = load(source / 'manifest.json')
    if manifest.get('schema_version') != 1 or not isinstance(manifest.get('files'), dict) or not manifest['files']:
        raise ValueError('Unsupported or empty sealed results archive')
    for name, expected in manifest['files'].items():
        relative = Path(name)
        target = source / relative
        if (not isinstance(expected, str) or not SHA256.fullmatch(expected)
                or relative.is_absolute() or '..' in relative.parts or name == 'manifest.json'
                or not target.is_file() or target.is_symlink()
                or not target.resolve().is_relative_to(source)
                or any(parent.is_symlink() for parent in target.parents if parent != source)
                or digest(target) != expected):
            raise ValueError('Archive integrity check failed: ' + name)
    actual = {p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()}
    if actual != set(manifest['files']) | {'manifest.json'}:
        raise ValueError('Archive contains missing or unmanifested files')
    if manifest.get('kind') == 'ploptimizer-results-bundle':
        from .bundle import load_bundle
        load_bundle(source)
        return manifest, 'historical'
    if {'run_id', 'expected_slots', 'result_count', 'complete'} <= manifest.keys() and 'results.json' in manifest['files']:
        document = load(source / 'results.json')
        if (document.get('run_id') != manifest['run_id'] or not isinstance(document.get('results'), list)
                or len(document['results']) != manifest['result_count']):
            raise ValueError('Native result count or run identity differs from manifest')
        identities = [(r['case']['id'], r['assembler']) for r in document['results']]
        if len(set(identities)) != len(identities):
            raise ValueError('Native archive contains duplicate execution identities')
        if manifest.get('expected_slot_plan') is not None:
            expected = {(r['case_id'], r['assembler']) for r in manifest['expected_slot_plan']}
            if expected != set(identities) or len(expected) != manifest['expected_slots']:
                raise ValueError('Native results differ from frozen slot plan')
        return manifest, 'nextflow'
    raise ValueError('Unknown results producer')


def import_archive(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or source in output.parents or output in source.parents:
        raise ValueError('Import source and destination must be separate directories')
    manifest, kind = validate_archive(source)
    if output.exists():
        raise ValueError('Import destination already exists; sealed archives are immutable')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.admit-', dir=output.parent) as temporary:
        staged = Path(temporary) / 'archive'
        shutil.copytree(source, staged)
        validate_archive(staged)
        staged.rename(output)
    receipt = {'schema_version': 1, 'kind': 'benchmark-results-import', 'producer': kind,
               'manifest_sha256': digest(output / 'manifest.json'),
               'file_count': len(manifest['files']),
               'retention': 'Every sealed source file is retained byte for byte. No analysis was run.'}
    save(output.with_name(output.name + '.import.json'), receipt)
    return receipt


def render_website(source, output):
    source, output = Path(source).resolve(), Path(output).resolve()
    _, kind = validate_archive(source)
    if kind == 'historical':
        from .bundle_render import render_bundle
        return render_bundle(source, output)
    from .native_site import render_native
    return render_native(source, output)
