"""Provision selected locked environments before scheduling benchmark tasks."""
import datetime
import fcntl
import hashlib
from pathlib import Path
import subprocess
import time

from .io import digest


class EnvironmentPreparationError(RuntimeError):
    def __init__(self, message, receipt):
        super().__init__(message)
        self.receipt = receipt


def _text_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def prepare_environments(project, plan, pixi='pixi'):
    """Install serially under a shared provisioning lock, never retrying jobs."""
    # Import here keeps runtime provisioning separate from catalogue validation.
    from .planning import validate_plan

    project = Path(project).resolve()
    validate_plan(project, plan)
    requested = {('environments/pixi.toml', 'default')}
    for definition in plan['assembler_definitions'].values():
        requested.add((definition['manifest'], definition['environment']))
    ordered = [('environments/pixi.toml', 'default')]
    ordered.extend(sorted(requested - set(ordered)))
    receipt = {'schema_version': 1, 'status': 'preparing', 'plan_sha256': plan['plan_sha256'],
               'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
               'policy': 'Locked environment preparation is serial before scheduling; assembler concurrency is unchanged.',
               'environments': [], 'automatic_retries': 0}
    lock = project / 'environments/.pixi/.benchmark-install.lock'
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('a') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        # Sources may have changed while waiting for another launcher to finish.
        validate_plan(project, plan)
        for manifest_name, environment in ordered:
            manifest = project / manifest_name
            lockfile = manifest.with_name('pixi.lock')
            row = {'manifest': manifest_name, 'environment': environment,
                   'manifest_sha256': digest(manifest), 'lock_sha256': digest(lockfile),
                   'command': [str(pixi), 'install', '--locked', '--manifest-path', str(manifest),
                               '--environment', environment]}
            receipt['environments'].append(row)
            started = time.monotonic()
            try:
                result = subprocess.run(row['command'], cwd=project, text=True, capture_output=True, check=True)
                row.update(status='prepared', exit_code=result.returncode,
                           stdout_sha256=_text_hash(result.stdout or ''),
                           stderr_sha256=_text_hash(result.stderr or ''))
                if digest(manifest) != row['manifest_sha256'] or digest(lockfile) != row['lock_sha256']:
                    raise ValueError('Locked manifest or lock file changed during preparation')
            except (OSError, ValueError, subprocess.CalledProcessError) as error:
                row.update(status='failed', error=f'{type(error).__name__}: {error}')
                if isinstance(error, subprocess.CalledProcessError):
                    row.update(exit_code=error.returncode, stdout=error.stdout or '', stderr=error.stderr or '')
                receipt['status'] = 'failed'
                receipt['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                raise EnvironmentPreparationError('Environment preparation failed before benchmark scheduling: ' + environment, receipt) from error
            finally:
                row['elapsed_seconds'] = time.monotonic() - started
        validate_plan(project, plan)
    receipt['status'] = 'prepared'
    receipt['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return receipt
