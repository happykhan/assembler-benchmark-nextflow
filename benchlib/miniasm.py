"""Pinned minimap2 overlaps → unpolished miniasm unitigs, with saved provenance."""
import argparse
import json
import collections
from pathlib import Path
import re
import subprocess
import time
import shutil

from .io import digest, save
from .adapters import verify_version


def extract_unitigs(raw, graph, assembly, require_length_tag=True):
    """Preserve sequences/links; retain miniasm a/x annotations in raw output."""
    seen = set()
    omitted = collections.Counter()
    with raw.open() as source, graph.open('w') as gfa, assembly.open('w') as fasta:
        for line in source:
            if not line.strip():
                continue
            fields = line.rstrip('\n').split('\t')
            kind = fields[0]
            if kind == 'S':
                if (len(fields) < 3 or fields[1] in seen or not re.fullmatch(r'[!-~]+', fields[1])
                        or not re.fullmatch(r'[ACGTRYSWKMBDHVNacgtryswkmbdhvn]+', fields[2])):
                    raise ValueError('Invalid, duplicate or sequence-less miniasm unitig')
                lengths = [f for f in fields[3:] if f.startswith('LN:i:')]
                if len(lengths) > 1 or (require_length_tag and not lengths) or (lengths and int(lengths[0][5:]) != len(fields[2])):
                    raise ValueError('Miniasm sequence and declared length disagree')
                seen.add(fields[1])
                fasta.write('>' + fields[1] + '\n' + fields[2] + '\n')
            elif kind in {'a', 'x'}:
                omitted[kind] += 1
                continue
            elif kind not in {'H', 'L', 'P'}:
                raise ValueError('Unexpected miniasm output record: ' + kind)
            gfa.write(line)
    return {'unitig_count': len(seen), 'raw_annotation_records': dict(omitted),
            'raw_gfa_sha256': digest(raw), 'graph_sha256': digest(graph),
            'assembly_sha256': digest(assembly),
            'conversion': 'FASTA copies S sequences verbatim; standard GFA retains H/S/L/P. Raw a/x annotations retained separately.'}


def run(reads, output, threads, polish=False, expected_versions=None):
    reads, output = Path(reads).resolve(), Path(output).resolve()
    started = time.monotonic()
    if threads < 1:
        raise ValueError('Threads must be positive')
    output.mkdir(parents=True, exist_ok=False)
    overlaps, raw = output / 'overlaps.paf', output / 'assembly.raw.gfa'
    steps = [
        {'name': 'Read-to-read overlaps', 'command': ['minimap2', '-x', 'ava-ont', '-t', str(threads), str(reads), str(reads)], 'stdout_file': str(overlaps)},
        {'name': 'Unpolished unitig assembly', 'command': ['miniasm', '-f', str(reads), str(overlaps)], 'stdout_file': str(raw)},
    ]
    record = {'schema_version': 1, 'status': 'running', 'steps': steps,
              'polishing': 'none', 'reads_sha256': digest(reads), 'versions': {},
              'expected_versions': expected_versions or {}, 'automatic_retries': 0}
    manifest = output / 'workflow.json'
    save(manifest, record)
    versions_verified = False
    try:
        binaries = [('minimap2', '--version'), ('miniasm', '-V')]
        if polish:
            binaries += [('minipolish', '--version'), ('racon', '--version')]
        if not expected_versions or any(binary not in expected_versions for binary, _ in binaries):
            raise ValueError('Exact versions are required for every workflow dependency')
        for binary, flag in binaries:
            version = subprocess.run([binary, flag], capture_output=True, text=True, check=True, timeout=30)
            record['versions'][binary] = (version.stdout + version.stderr).strip()
            verify_version(record['versions'][binary], expected_versions[binary], binary)
        record['status'] = 'running'
        versions_verified = True
        for index, step in enumerate(steps):
            save(manifest, record)
            step_started = time.monotonic()
            with Path(step['stdout_file']).open('w') as stdout, (output / f'step-{index + 1}.stderr.log').open('w') as stderr:
                completed = subprocess.run(step['command'], stdout=stdout, stderr=stderr)
            step['elapsed_seconds'] = time.monotonic() - step_started
            step['exit_code'] = completed.returncode
            step['stdout_sha256'] = digest(Path(step['stdout_file']))
            step['stderr_sha256'] = digest(output / f'step-{index + 1}.stderr.log')
            step['stderr_tail'] = (output / f'step-{index + 1}.stderr.log').read_text(errors='replace')[-4000:]
            if completed.returncode:
                raise RuntimeError(step['name'] + ' failed with exit code ' + str(completed.returncode))
        record['conversion'] = extract_unitigs(raw, output / 'assembly_graph.gfa', output / 'assembly.fasta')
        record['overlaps_sha256'] = digest(overlaps)
        record['status'] = 'complete'
        record['elapsed_seconds'] = time.monotonic() - started
        raw_dir = output / 'raw-phase'
        raw_dir.mkdir()
        for name in ('assembly.fasta', 'assembly_graph.gfa', 'assembly.raw.gfa'):
            shutil.copyfile(output / name, raw_dir / name)
        save(raw_dir / 'execution.json', dict(record, phase='raw_miniasm', reported_outcome=False))
        record['raw_phase_execution_sha256'] = digest(raw_dir / 'execution.json')
        record['raw_phase_reported_outcome'] = False
        if polish and record['conversion']['unitig_count']:
            polished = output / 'assembly.polished.gfa'
            command = ['minipolish', '--threads', str(threads), '--rounds', '2', str(reads), str(raw)]
            step = {'name': 'Minipolish initial polish and two full rounds', 'command': command}
            record['steps'].append(step)
            step_started = time.monotonic()
            with polished.open('w') as stdout, (output / 'minipolish.stderr.log').open('w') as stderr:
                result = subprocess.run(command, stdout=stdout, stderr=stderr)
            step['elapsed_seconds'] = time.monotonic() - step_started
            step['exit_code'] = result.returncode
            step['stdout_sha256'] = digest(polished)
            step['stderr_sha256'] = digest(output / 'minipolish.stderr.log')
            if result.returncode:
                raise RuntimeError('Minipolish failed with exit code ' + str(result.returncode))
            record['conversion'] = extract_unitigs(polished, output / 'assembly_graph.gfa', output / 'assembly.fasta', require_length_tag=False)
            record['polishing'] = 'Initial constituent-read polish plus two full Racon rounds'
        elif polish:
            record['polishing'] = 'not_run_empty_raw_assembly'
        record['elapsed_seconds'] = time.monotonic() - started
    except Exception as error:
        record.update(status='software_error' if versions_verified else 'infrastructure_error',
                      error=f'{type(error).__name__}: {error}')
        raise
    finally:
        record['elapsed_seconds'] = time.monotonic() - started
        record['retained_file_sha256'] = {p.relative_to(output).as_posix(): digest(p) for p in output.rglob('*')
            if p.is_file() and p != manifest}
        save(manifest, record)
    return record


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reads', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--threads', type=int, required=True)
    parser.add_argument('--polish', action='store_true')
    parser.add_argument('--expected-versions-json', required=True)
    args = parser.parse_args()
    run(args.reads, args.output, args.threads, args.polish, json.loads(args.expected_versions_json))
