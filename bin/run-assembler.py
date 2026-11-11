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


VERSIONS = {'flye': '2.9.6', 'raven': '1.8.3'}


def run(assembler, reads, directory, cpus):
    if cpus < 1:
        raise ValueError('cpus must be positive')
    reads = Path(reads).resolve()
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    record_path = directory / 'execution.json'
    record = {'schema_version': 1, 'status': 'infrastructure_error', 'assembler': assembler,
              'expected_version': VERSIONS[assembler], 'cpus': cpus,
              'started_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'automatic_retries': 0}
    try:
        project = Path(__file__).resolve().parents[1]
        record['environment_lock_sha256'] = digest(project / 'environments/pixi.lock')
        record['adapter_source_sha256'] = digest(Path(__file__).resolve())
        record['support_source_sha256'] = {
            name: digest(project / name) for name in ('benchlib/io.py', 'benchlib/process.py')}
        record['reads_sha256'] = digest(reads)
        version = subprocess.check_output([assembler, '--version'], text=True, stderr=subprocess.STDOUT).strip()
        record['version'] = version
        if version != VERSIONS[assembler] and not version.startswith(VERSIONS[assembler] + '-'):
            raise ValueError('Pinned version mismatch: ' + version)
        if assembler == 'flye':
            command = ['flye', '--nano-raw', str(reads), '--out-dir', 'tool-output', '--threads', str(cpus)]
        else:
            command = ['raven', '--threads', str(cpus), '--graphical-fragment-assembly', 'assembly.gfa', str(reads)]
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
            source = directory / ('tool-output/assembly.fasta' if assembler == 'flye' else 'stdout.log')
            assembly = directory / 'assembly.fasta'
            if source.is_file():
                empty = source.stat().st_size == 0
                if not empty:
                    fasta_lengths(source)
                shutil.copyfile(source, assembly)
                record.update(status='completed', assembly_path='assembly.fasta', assembly_sha256=digest(assembly),
                              assembly_state='empty' if empty else 'nonempty')
                graph = directory / ('tool-output/assembly_graph.gfa' if assembler == 'flye' else 'assembly.gfa')
                if graph.is_file():
                    if assembler == 'flye':
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
    parser.add_argument('--assembler', choices=sorted(VERSIONS), required=True)
    parser.add_argument('--reads', required=True)
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--cpus', type=int, default=2)
    args = parser.parse_args()
    result = run(args.assembler, args.reads, args.out_dir, args.cpus)
    sys.exit(1 if result['status'] == 'infrastructure_error' else 0)
