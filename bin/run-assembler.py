#!/usr/bin/env python3
"""Run a pinned assembler once, preserving successful and failed outcomes."""
import argparse
import datetime
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchlib.io import digest, fasta_lengths, save
from benchlib.process import measured_run
from benchlib.adapters import ADAPTERS, load_registry, resolve_assembler, validate_environment


PROJECT = Path(__file__).resolve().parents[1]
REGISTRY = PROJECT / 'assets/assemblers.json'


def run(assembler, reads, directory, cpus, registry_path=REGISTRY):
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
              'automatic_retries': 0}
    try:
        project = PROJECT
        manifest = validate_environment(definition, project)
        record['environment_lock_sha256'] = digest(manifest.with_suffix('.lock'))
        record['environment_manifest_sha256'] = digest(manifest)
        record['registry_sha256'] = digest(registry_path)
        record['adapter_source_sha256'] = digest(Path(__file__).resolve())
        record['support_source_sha256'] = {
            name: digest(project / name) for name in ('benchlib/io.py', 'benchlib/process.py', 'benchlib/adapters.py')}
        record['reads_sha256'] = digest(reads)
        version = subprocess.check_output([adapter.executable, '--version'], text=True, stderr=subprocess.STDOUT).strip()
        record['version'] = version
        if version != definition['version'] and not version.startswith(definition['version'] + '-'):
            raise ValueError('Pinned version mismatch: ' + version)
        command = adapter.command(reads, cpus)
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
                shutil.copyfile(source, assembly)
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
    args = parser.parse_args()
    result = run(args.assembler, args.reads, args.out_dir, args.cpus, args.registry)
    sys.exit(1 if result['status'] == 'infrastructure_error' else 0)
