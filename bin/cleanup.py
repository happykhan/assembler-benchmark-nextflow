#!/usr/bin/env python3
"""Offer guarded Nextflow work cleanup, with a dry run as the default.

Removing work prevents Nextflow resume. Reference caches and retained bundles
are never cleanup targets. Launch and cleanup share an exclusive lifecycle lock.
"""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil

MARKER = '.assembler-benchmark-work.json'
ACTIVE = '.benchmark-active'
LOCK = '.benchmark-cleanup.lock'
REPOSITORY = Path(__file__).resolve().parents[1]


def validate_paths(work_dir, bundle, reference_dir=None, outdir=None):
    """Resolve aliases before checking every protected ancestor and overlap."""
    work_dir, bundle = Path(work_dir), Path(bundle)
    if work_dir.is_symlink() or bundle.is_symlink():
        raise ValueError('Work and bundle paths cannot be symbolic links')
    work, bundle = work_dir.resolve(), bundle.resolve()
    protected = (Path('/'), Path.home().resolve(), REPOSITORY)
    if any(work == path or path.is_relative_to(work) for path in protected):
        raise ValueError('Work path is a protected directory or its ancestor')
    for other, label in ((bundle, 'bundle'), (outdir, 'output directory'),
                         (reference_dir, 'reference cache')):
        if other is None:
            continue
        other = Path(other).resolve()
        if work == other or other.is_relative_to(work) or work.is_relative_to(other):
            raise ValueError('Work directory overlaps the protected ' + label)
    return work, bundle


@contextmanager
def lifecycle_lock(work):
    """Keep the lock inode outside work so deleting work cannot bypass it."""
    lock_path = work.parent / ('.' + work.name + '.benchmark-launch.lock')
    flags = os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW
    descriptor = os.open(lock_path, flags, 0o600)
    with os.fdopen(descriptor, 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError('Another workflow launch or cleanup owns this work directory') from error
        yield


def load(path):
    with path.open() as stream:
        return json.load(stream)


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def retained_file(bundle, relative):
    """Only ordinary files below the bundle can be evidence."""
    if not isinstance(relative, str):
        raise ValueError('Manifest file names must be relative strings')
    name = Path(relative)
    if name.is_absolute() or '..' in name.parts or not name.parts:
        raise ValueError('Unsafe manifest path: ' + relative)
    path = bundle / name
    for component in [path, *path.parents]:
        if component == bundle:
            break
        if component.is_symlink():
            raise ValueError('Retained evidence cannot be a symbolic link: ' + relative)
    if not path.is_file() or not path.resolve().is_relative_to(bundle):
        raise ValueError('Missing or escaped retained file: ' + relative)
    return path


def validate_bundle(bundle):
    manifest_path = retained_file(bundle, 'manifest.json')
    manifest = load(manifest_path)
    if manifest.get('complete') is not True:
        raise ValueError('Bundle is incomplete; work must be retained')
    run_id = manifest.get('run_id')
    if not isinstance(run_id, str) or not run_id:
        raise ValueError('Bundle has no run ID')
    expected, count = manifest.get('expected_slots'), manifest.get('result_count')
    if type(expected) is not int or expected < 1 or count != expected:
        raise ValueError('Expected result slots have not all been accounted for')
    files = manifest.get('files')
    if not isinstance(files, dict) or not files:
        raise ValueError('Bundle has no retained-file checksum index')
    for relative, checksum in files.items():
        if not isinstance(checksum, str) or len(checksum) != 64:
            raise ValueError('Invalid checksum for ' + relative)
        if sha256(retained_file(bundle, relative)) != checksum:
            raise ValueError('Retained file checksum mismatch: ' + relative)
    actual = set()
    for path in bundle.rglob('*'):
        if path.is_symlink():
            raise ValueError('Bundle contains a symbolic link: ' + str(path))
        if path.is_file() and path != manifest_path:
            actual.add(path.relative_to(bundle).as_posix())
    if actual != set(files):
        raise ValueError('Checksum index does not cover every retained bundle file')
    if 'results.json' not in files:
        raise ValueError('Bundle does not retain its machine-readable results')
    results = load(bundle / 'results.json')
    if isinstance(results, dict):
        results = results.get('results')
    if not isinstance(results, list) or len(results) != expected:
        raise ValueError('Machine-readable result count differs from expected slots')
    keys, completed = set(), 0
    for result in results:
        case = result.get('case', {})
        key = (case.get('id'), result.get('assembler'))
        if not all(isinstance(v, str) and v for v in key) or key in keys:
            raise ValueError('Missing or duplicate result slot')
        keys.add(key)
        status = result.get('execution', {}).get('status')
        assessment = result.get('assessment', {}).get('status')
        if status not in ('completed', 'software_error'):
            raise ValueError('Infrastructure or unfinished execution prevents cleanup')
        if status == 'completed':
            completed += 1
            if assessment != 'completed':
                raise ValueError('Failed or unfinished assessment prevents cleanup')
        elif assessment != 'not_run':
            raise ValueError('Software failure has an inconsistent assessment status')
    retention = manifest.get('retention', {})
    if 'expected_slot_plan' in manifest:
        expected = [(row.get('case_id'), row.get('assembler')) for row in manifest['expected_slot_plan']]
        if len(expected) != len(set(expected)) or set(expected) != keys:
            raise ValueError('Result identities differ from frozen expected slots')
    assemblies, graphs = retention.get('assemblies'), retention.get('graphs')
    if not isinstance(assemblies, list) or not isinstance(graphs, list):
        raise ValueError('Final assembly and graph retention must be explicit')
    if len(set(assemblies)) != len(assemblies) or len(assemblies) < completed:
        raise ValueError('Successful executions are missing retained final assemblies')
    for relative in assemblies + graphs:
        if relative not in files:
            raise ValueError('Final output lacks checksum evidence: ' + relative)
        retained_file(bundle, relative)
    return manifest


def validate_work(work_dir, bundle, manifest):
    work, bundle = validate_paths(work_dir, bundle)
    marker_path = work / MARKER
    if not work.is_dir() or marker_path.is_symlink() or not marker_path.is_file():
        raise ValueError('Work directory has no valid ownership marker')
    marker = load(marker_path)
    if marker.get('run_id') != manifest['run_id']:
        raise ValueError('Work directory belongs to a different run')
    if marker.get('bundle_path') != str(bundle):
        raise ValueError('Work directory marker names a different bundle')
    reference_dir = marker.get('reference_dir')
    if not isinstance(reference_dir, str) or not Path(reference_dir).is_absolute():
        raise ValueError('Work marker does not identify the protected reference cache')
    validate_paths(work, bundle, reference_dir=reference_dir)
    if (work / ACTIVE).exists() or (work / ACTIVE).is_symlink():
        raise ValueError('A workflow is active; work cannot be removed')
    return work


def cleanup(bundle_path, work_path, apply=False, confirm_run_id=None):
    bundle = Path(bundle_path)
    if bundle.is_symlink():
        raise ValueError('Bundle path cannot be a symbolic link')
    bundle = bundle.resolve()
    manifest = validate_bundle(bundle)
    work = validate_work(Path(work_path), bundle, manifest)
    if apply and confirm_run_id != manifest['run_id']:
        raise ValueError('--apply also requires --confirm-run-id matching this bundle')
    with lifecycle_lock(work):
        # Validate again under the same lock the launcher holds throughout its
        # subprocess. A stale preliminary validation cannot authorise deletion.
        manifest = validate_bundle(bundle)
        validate_work(work, bundle, manifest)
        if apply and confirm_run_id != manifest['run_id']:
            raise ValueError('--apply also requires --confirm-run-id matching this bundle')
        lock = work / LOCK
        try:
            lock.mkdir()
        except FileExistsError as error:
            raise ValueError('Another cleanup is in progress; inspect the existing lock') from error
        try:
            files = [p for p in work.rglob('*') if p.is_file() and not p.is_symlink()]
            report = {'run_id': manifest['run_id'], 'action': 'delete' if apply else 'dry_run',
                      'candidate': str(work), 'file_count': len(files),
                      'bytes': sum(p.stat().st_size for p in files),
                      'retained_bundle': str(bundle),
                      'warning': 'Deleting Nextflow work prevents resume. Shared references are retained.'}
            if apply:
                validate_bundle(bundle)
                validate_work(work, bundle, manifest)
                shutil.rmtree(work)
            return report
        finally:
            if lock.exists():
                lock.rmdir()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirm-run-id')
    args = parser.parse_args()
    try:
        result = cleanup(args.bundle, args.work_dir, args.apply, args.confirm_run_id)
    except (ValueError, OSError, json.JSONDecodeError) as error:
        parser.exit(2, 'Cleanup refused: ' + str(error) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
