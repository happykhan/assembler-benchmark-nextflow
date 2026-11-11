#!/usr/bin/env python3
"""Launch an owned resumable Quick run with cleanup guards."""
import argparse
import json
from pathlib import Path
import re
import subprocess
from cleanup import ACTIVE, LOCK, MARKER, lifecycle_lock, validate_bundle, validate_paths


def validate_nextflow_args(arguments):
    """Passthrough flags cannot change the run identity or owned directories."""
    protected = {'--run_id', '--run-id', '--outdir', '--reference_dir',
                 '--reference-dir', '--work_dir', '--work-dir', '-w', '-work-dir'}
    for argument in arguments:
        option = argument.split('=', 1)[0]
        # Nextflow also accepts joined short option values such as -w/path.
        joined_work = option.startswith('-w') and not option.startswith(('-with-', '-work'))
        if option in protected or joined_work or option.startswith('-work-dir'):
            raise ValueError('Pass owned run/directory settings to the launcher, not Nextflow: ' + option)
    return arguments


def launch_run(run_id, outdir, work_dir, reference_dir, nextflow='nextflow', nextflow_args=()):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', run_id):
        raise ValueError('Use a simple run ID containing letters, digits, dots, hyphens or underscores')
    extra = list(nextflow_args)
    if extra[:1] == ['--']:
        extra = extra[1:]
    validate_nextflow_args(extra)
    root = Path(__file__).resolve().parents[1]
    outdir, references = Path(outdir).resolve(), Path(reference_dir).resolve()
    work, bundle = validate_paths(work_dir, outdir / 'bundle', references, outdir)
    work.parent.mkdir(parents=True, exist_ok=True)
    with lifecycle_lock(work):
        work.mkdir(exist_ok=True)
        if (work / LOCK).exists():
            raise ValueError('Cleanup is in progress; inspect the cleanup marker')
        marker = work / MARKER
        identity = {'run_id': run_id, 'bundle_path': str(bundle), 'reference_dir': str(references)}
        if marker.is_symlink():
            raise ValueError('Work ownership marker cannot be a symbolic link')
        if marker.exists() and json.loads(marker.read_text()) != identity:
            raise ValueError('Work directory belongs to another run or output destination')
        if not marker.exists() and any(work.iterdir()):
            raise ValueError('Refusing to take ownership of an existing non-empty work directory')
        marker.write_text(json.dumps(identity, indent=2) + '\n')
        active = work / ACTIVE
        if active.is_symlink():
            raise ValueError('Active-run marker cannot be a symbolic link')
        active.write_text(run_id + '\n')
        command = [nextflow, 'run', str(root / 'main.nf'), '-w', str(work),
                   '--run_id', run_id, '--outdir', str(outdir),
                   '--reference_dir', str(references)] + extra
        result = subprocess.run(command)
        if result.returncode == 0:
            manifest = validate_bundle(bundle)
            if manifest['run_id'] != run_id:
                raise ValueError('Exported bundle belongs to a different run')
            active.unlink()
        return result.returncode


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-id', required=True)
    p.add_argument('--outdir', type=Path, default=Path('results/quick'))
    p.add_argument('--work-dir', type=Path, default=Path('work/quick'))
    p.add_argument('--reference-dir', type=Path, default=Path('references'))
    p.add_argument('--nextflow', default='nextflow')
    p.add_argument('nextflow_args', nargs=argparse.REMAINDER)
    a = p.parse_args()
    try:
        code = launch_run(a.run_id, a.outdir, a.work_dir, a.reference_dir,
                          a.nextflow, a.nextflow_args)
    except (ValueError, OSError, json.JSONDecodeError) as error:
        p.error(str(error))
    raise SystemExit(code)


if __name__ == '__main__':
    main()
