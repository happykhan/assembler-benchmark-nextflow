"""Retain bound workflow phases and original final-output constituents."""
from pathlib import Path
import shutil
from .io import digest


def retain_workflow_evidence(execution, directory, evidence):
    directory, evidence = Path(directory), Path(evidence)
    sources = {}
    workflow = execution.get('assembly_workflow')
    if workflow is not None:
        sources['tool-output/workflow.json'] = execution.get('assembly_workflow_sha256')
        for name, checksum in workflow.get('retained_file_sha256', {}).items():
            # Large all-read overlap mappings remain in the task cache. Preserve
            # their checksum in workflow.json; raw assemblies and logs are portable.
            if Path(name).suffix in ('.fasta', '.gfa', '.json', '.log'):
                sources['tool-output/' + name] = checksum
    for source in execution.get('assembly_sources', []):
        sources[source['file']] = source['sha256']
    retained, graphs = [], []
    for name, expected in sorted(sources.items()):
        relative = Path(name)
        source = directory / relative
        if relative.is_absolute() or '..' in relative.parts or source.is_symlink() or not source.resolve().is_relative_to(directory.resolve()):
            raise ValueError('Unsafe workflow evidence path')
        if not expected or not source.is_file() or digest(source) != expected:
            raise ValueError('Workflow evidence binding differs: ' + name)
        target = 'workflow__' + '__'.join(relative.parts)
        shutil.copyfile(source, evidence / target)
        retained.append({'source_file': name, 'file': target, 'sha256': expected})
        if source.suffix == '.gfa':
            graphs.append({'file': target, 'sha256': expected, 'role': 'raw_phase_or_workflow_graph'})
    return retained, graphs
