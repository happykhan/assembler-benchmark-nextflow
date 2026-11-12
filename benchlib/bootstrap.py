"""Native Nextflow setup: freeze selection, validate reuse, provision software."""
import json
from pathlib import Path

from .planning import build_plan, validate_plan
from .runtime import prepare_environments


def prepare_run(project, selection, runtime, supplied_plan=None, existing_plan=None):
    if runtime not in ('pixi', 'native'):
        raise ValueError('Use the admitted Pixi runtime or explicitly prepared native tools')
    if supplied_plan:
        if selection.get('track', 'simulated') != 'simulated':
            raise ValueError('An existing plan cannot be combined with track selection')
        if selection.get('preset', 'quick') != 'quick' or any(selection.get(k) for k in ('groups', 'cases', 'assemblers')):
            raise ValueError('An existing plan cannot be combined with new selections')
        plan = validate_plan(project, json.loads(Path(supplied_plan).read_text()))
    else:
        plan = build_plan(project, **selection)
    if existing_plan and Path(existing_plan).exists():
        existing = validate_plan(project, json.loads(Path(existing_plan).read_text()))
        if existing != plan:
            raise ValueError('Output directory contains a different selection; choose a new --outdir')
    receipt = (prepare_environments(project, plan) if runtime == 'pixi' else
               {'status': 'externally_prepared', 'runtime': 'native', 'plan_sha256': plan['plan_sha256']})
    return plan, receipt
