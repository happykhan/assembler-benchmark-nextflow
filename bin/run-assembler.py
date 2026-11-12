#!/usr/bin/env python3
"""Run a pinned assembler once, preserving successful and failed outcomes."""
import argparse
import json
import datetime
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchlib.io import digest, fasta_lengths, save
from benchlib.process import measured_run
from benchlib.adapters import ADAPTERS, load_registry, resolve_assembler, validate_environment, validate_options, verify_version, environment_versions


PROJECT = Path(__file__).resolve().parents[1]
REGISTRY = PROJECT / 'assets/assemblers.json'


def run(assembler, reads, directory, cpus, registry_path=REGISTRY, options=None):
    options = validate_options(options)
    if cpus < 1:
        raise ValueError('cpus must be positive')
    definition = resolve_assembler(load_registry(registry_path), assembler)
    adapter = ADAPTERS[definition['adapter']]
    reads = Path(reads).resolve()
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    record_path = directory / 'execution.json'
    record = {'schema_version': 1, 'status': 'infrastructure_error', 'assembler': definition['id'],
              'tool': definition['tool'], 'adapter': definition['adapter'],
              'environment': definition['environment'], 'manifest': definition['manifest'],
              'expected_version': definition['version'], 'cpus': cpus,
              'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'automatic_retries': 0, 'options': options}
    try:
        project = PROJECT
        manifest = validate_environment(definition, project)
        record['environment_lock_sha256'] = digest(manifest.with_suffix('.lock'))
        record['environment_manifest_sha256'] = digest(manifest)
        record['registry_sha256'] = digest(registry_path)
        record['adapter_source_sha256'] = digest(Path(__file__).resolve())
        record['support_source_sha256'] = {
            name: digest(project / name) for name in ('benchlib/io.py', 'benchlib/process.py', 'benchlib/adapters.py', 'benchlib/miniasm.py', 'bin/run-miniasm.py')}
        record['reads_sha256'] = digest(reads)
        version = subprocess.check_output([adapter.executable, '-V' if definition['tool'] == 'miniasm' else '--version'], text=True, stderr=subprocess.STDOUT, timeout=30).strip()
        record['version'] = version
        verify_version(version, definition['version'], adapter.executable)
        command = adapter.command(reads, cpus, options)
        if definition['tool'] in ('miniasm', 'miniasm-plus'):
            command = [sys.executable, str(project / 'bin/run-miniasm.py'), '--reads', str(reads),
                       '--output', 'tool-output', '--threads', str(cpus),
                       '--expected-versions-json', json.dumps(environment_versions(definition, project), sort_keys=True)]
            if definition['tool'] == 'miniasm-plus':
                command.append('--polish')
        record['command'] = command
        save(record_path, dict(record, status='running'))
        measurement = measured_run(command, directory / 'stdout.log', directory / 'stderr.log', directory)
        record['tool_elapsed_seconds'] = measurement.pop('elapsed_seconds')
        record.update(measurement)
        record['status'] = 'software_error'
        if measurement['exit_code'] != 0:
            record['status'] = 'software_error'
            record['error'] = 'Assembler exited with non-zero status; original attempt retained without retry'
        else:
            source = directory / adapter.assembly_relative
            assembly = directory / 'assembly.fasta'
            if source.is_file():
                empty = source.stat().st_size == 0
                if not empty:
                    fasta_lengths(source)
                if definition['tool'] == 'plassembler':
                    from benchlib.assessment import read_fasta
                    sources = [('final_plasmids', source)]
                    chromosome = directory / 'tool-output/chromosome.fasta'
                    if not options.get('plassembler_no_chromosome') and chromosome.is_file():
                        sources.append(('retained_chromosome', chromosome))
                        record['retained_chromosome_sha256'] = digest(chromosome)
                    record['assembly_sources'], record['contig_sources'] = [], []
                    with assembly.open('w') as target:
                        for role, original in sources:
                            record['assembly_sources'].append({'role': role, 'file': str(original.relative_to(directory)),
                                'sha256': digest(original), 'bytes': original.stat().st_size})
                            if not original.stat().st_size:
                                continue
                            sequences = read_fasta(original)
                            if not sequences:
                                raise ValueError('Nonempty Plassembler FASTA has no records')
                            for name, sequence in sequences.items():
                                identifier = role + ':' + name
                                target.write('>' + identifier + '\n' + sequence + '\n')
                                record['contig_sources'].append({'contig_id': identifier,
                                    'source_role': role, 'source_contig_id': name})
                    empty = assembly.stat().st_size == 0
                    record['assessed_output_scope'] = 'Final plasmids plus actual retained chromosome'
                else:
                    shutil.copyfile(source, assembly)
                workflow = directory / 'tool-output/workflow.json'
                if workflow.is_file():
                    record['assembly_workflow'] = json.loads(workflow.read_text())
                record.update(status='completed', assembly_path='assembly.fasta', assembly_sha256=digest(assembly),
                              assembly_state='empty' if empty else 'nonempty')
                graph = directory / adapter.graph_relative
                if graph.is_file():
                    if graph != directory / 'assembly.gfa':
                        shutil.copyfile(graph, directory / 'assembly.gfa')
                    record.update(graph_path='assembly.gfa', graph_sha256=digest(directory / 'assembly.gfa'))
            else:
                record.update(status='software_error', error='Assembler exited successfully without its required final FASTA file')
    except Exception as error:
        record['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        workflow = directory / 'tool-output/workflow.json'
        if workflow.is_file():
            try:
                record['assembly_workflow'] = json.loads(workflow.read_text())
                record['assembly_workflow_sha256'] = digest(workflow)
                if record['assembly_workflow'].get('reads_sha256') != record.get('reads_sha256'):
                    raise ValueError('Workflow/input read checksum binding differs')
                if record['assembly_workflow'].get('status') == 'infrastructure_error':
                    record['status'] = 'infrastructure_error'
            except (OSError, ValueError) as error:
                record.update(status='infrastructure_error', error='Invalid saved workflow metadata: ' + str(error))
        record['log_sha256'] = {name: digest(directory / name) for name in ('stdout.log', 'stderr.log')
                                if (directory / name).is_file()}
        record['elapsed_seconds'] = time.monotonic() - started
        record['wall_time_scope'] = 'Input/source/environment verification, version check, assembler invocation and final output verification; excludes scheduler waiting and downloads'
        record['finished_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        save(record_path, record)
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assembler', required=True, help='Admitted immutable version ID or declared alias')
    parser.add_argument('--registry', type=Path, default=REGISTRY)
    parser.add_argument('--reads', required=True)
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--cpus', type=int, default=2)
    parser.add_argument('--options-json', default='{}')
    args = parser.parse_args()
    result = run(args.assembler, args.reads, args.out_dir, args.cpus, args.registry, json.loads(args.options_json))
    sys.exit(1 if result['status'] == 'infrastructure_error' else 0)
