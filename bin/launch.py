#!/usr/bin/env python3
"""Launch an owned resumable Quick run with cleanup guards."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchlib.planning import build_plan, validate_plan
from benchlib.runtime import EnvironmentPreparationError, prepare_environments
from cleanup import ACTIVE, LOCK, MARKER, lifecycle_lock, validate_bundle, validate_paths
from cleanup import sha256


def validate_nextflow_args(arguments):
    """Passthrough flags cannot change the run identity or owned directories."""
    protected = {'--run_id', '--run-id', '--outdir', '--reference_dir',
                 '--reference-dir', '--work_dir', '--work-dir', '-w', '-work-dir',
                 '--plan', '--preset', '--groups', '--cases', '--assemblers'}
    for argument in arguments:
        option = argument.split('=', 1)[0]
        # Nextflow also accepts joined short option values such as -w/path.
        joined_work = option.startswith('-w') and not option.startswith(('-with-', '-work'))
        if option in protected or joined_work or option.startswith('-work-dir'):
            raise ValueError('Pass owned run/directory settings to the launcher, not Nextflow: ' + option)
    return arguments


def runtime_profiles(arguments):
    profiles = set()
    for index, argument in enumerate(arguments):
        if argument == '-profile':
            if index + 1 == len(arguments):
                raise ValueError('-profile requires a value')
            profiles.update(arguments[index + 1].split(','))
        elif argument.startswith('-profile='):
            profiles.update(argument.split('=', 1)[1].split(','))
    runtimes = profiles & {'pixi', 'docker', 'apptainer'}
    if len(runtimes) > 1:
        raise ValueError('Choose exactly one runtime profile')
    return runtimes


def launch_run(run_id, outdir, work_dir, reference_dir, nextflow='nextflow', nextflow_args=(),
               *, preset='quick', groups=None, cases=None, assemblers=None, plan_path=None):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]*', run_id):
        raise ValueError('Use a simple run ID containing letters, digits, dots, hyphens or underscores')
    extra = list(nextflow_args)
    if extra[:1] == ['--']:
        extra = extra[1:]
    validate_nextflow_args(extra)
    runtimes = runtime_profiles(extra)
    root = Path(__file__).resolve().parents[1]
    outdir, references = Path(outdir).resolve(), Path(reference_dir).resolve()
    work, bundle = validate_paths(work_dir, outdir / 'bundle', references, outdir)
    if plan_path:
        if preset != 'quick' or any((groups, cases, assemblers)):
            raise ValueError('An existing plan cannot be combined with new selections')
        plan = validate_plan(root, json.loads(Path(plan_path).read_text()))
    else:
        plan = build_plan(root, preset, groups, cases, assemblers)
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
        outdir.mkdir(parents=True, exist_ok=True)
        frozen_plan = outdir / 'selected-plan.json'
        if frozen_plan.is_symlink():
            raise ValueError('Frozen plan cannot be a symbolic link')
        if frozen_plan.exists():
            if json.loads(frozen_plan.read_text()) != plan:
                raise ValueError('Run plan changed; choose a new run ID and output/work directories')
        else:
            with frozen_plan.open('x') as stream:
                json.dump(plan, stream, indent=2, sort_keys=True, allow_nan=False)
                stream.write('\n')
        marker.write_text(json.dumps(identity, indent=2) + '\n')
        active = work / ACTIVE
        if active.is_symlink():
            raise ValueError('Active-run marker cannot be a symbolic link')
        active.write_text(run_id + '\n')
        if 'pixi' in runtimes:
            try:
                receipt = prepare_environments(root, plan)
            except EnvironmentPreparationError as error:
                (outdir / 'environment-preparation.json').write_text(json.dumps(error.receipt, indent=2, sort_keys=True) + '\n')
                raise
            (outdir / 'environment-preparation.json').write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
        command = [nextflow, 'run', str(root / 'main.nf'), '-w', str(work),
                   '--run_id', run_id, '--outdir', str(outdir),
                   '--reference_dir', str(references), '--plan', str(frozen_plan)] + extra
        result = subprocess.run(command)
        if result.returncode == 0:
            manifest = validate_bundle(bundle)
            if manifest['run_id'] != run_id:
                raise ValueError('Exported bundle belongs to a different run')
            if manifest.get('plan_sha256') != sha256(frozen_plan):
                raise ValueError('Exported bundle does not bind the frozen run plan')
            if manifest.get('expected_slots') != plan['expected_slots'] or manifest.get('expected_slot_plan') != plan['slots']:
                # Export order is canonical; compare slot sets independently of ordering.
                expected = {(row['case_id'], row['assembler']) for row in plan['slots']}
                actual = {(row['case_id'], row['assembler']) for row in manifest.get('expected_slot_plan', [])}
                if manifest.get('expected_slots') != plan['expected_slots'] or actual != expected:
                    raise ValueError('Exported bundle differs from the frozen expected slots')
            active.unlink()
        return result.returncode


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-id', required=True)
    p.add_argument('--outdir', type=Path, default=Path('results/quick'))
    p.add_argument('--work-dir', type=Path, default=Path('work/quick'))
    p.add_argument('--reference-dir', type=Path, default=Path('references'))
    p.add_argument('--nextflow', default='nextflow')
    p.add_argument('--plan', type=Path, help='Use an existing verified plan without changing its selection')
    p.add_argument('--preset', choices=('quick', 'standard'), default='quick')
    p.add_argument('--groups', default='')
    p.add_argument('--cases', default='')
    p.add_argument('--assemblers', default='')
    p.add_argument('nextflow_args', nargs=argparse.REMAINDER)
    a = p.parse_args()
    try:
        code = launch_run(a.run_id, a.outdir, a.work_dir, a.reference_dir,
                          a.nextflow, a.nextflow_args, preset=a.preset, groups=a.groups,
                          cases=a.cases, assemblers=a.assemblers, plan_path=a.plan)
    except (ValueError, RuntimeError, OSError, json.JSONDecodeError) as error:
        p.error(str(error))
    raise SystemExit(code)


if __name__ == '__main__':
    main()
