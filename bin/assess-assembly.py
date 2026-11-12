#!/usr/bin/env python3
"""Assess retained assemblies without converting execution errors to absence."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchlib.assessment import METHOD, outcome, parse_paf, read_fasta, sha256, summarise, write_json
from benchlib.process import measured_run
from benchlib.evidence import retain_workflow_evidence
from benchlib.paper_recovery import assess_paper


def retain_tool_evidence(execution, directory, evidence):
    """Preserve logs on failure and identify final versus partial graph evidence."""
    for name in ('stdout.log', 'stderr.log'):
        source = directory / name
        if source.is_file():
            shutil.copyfile(source, evidence / name)
    declared = execution.get('graph_path')
    if declared and (Path(declared).name != declared or Path(declared).suffix != '.gfa'):
        raise ValueError('Graph path must be a sibling GFA file')
    if declared and not (directory / declared).is_file():
        raise ValueError('Declared graph is missing')
    graphs = []
    for source in sorted(directory.glob('*.gfa')):
        if not source.is_file():
            continue
        checksum = sha256(source)
        if source.name == declared and checksum != execution.get('graph_sha256'):
            raise ValueError('Graph differs from execution hash')
        shutil.copyfile(source, evidence / source.name)
        graphs.append({'file': source.name, 'sha256': checksum,
                       'role': 'final_graph' if source.name == declared and execution.get('status') == 'completed' else 'partial_or_diagnostic_graph'})
    return graphs


def assess(args):
    started = time.monotonic()
    case = json.loads(args.case_json)
    execution = json.loads(args.execution.read_text())
    input_path = getattr(args, 'input_provenance', None) or args.simulation
    real = case.get('track') == 'real'
    external = case.get('track') in ('real', 'general')
    input_name = 'input-provenance.json' if external else 'simulation.json'
    input_key = 'input_provenance_sha256' if external else 'simulation_sha256'
    simulation = json.loads(input_path.read_text())
    provenance = json.loads(args.reference_provenance.read_text())
    output = args.out.resolve()
    evidence = output.with_name(output.stem + '.evidence')
    evidence.mkdir(parents=True, exist_ok=False)
    for source, name in ((args.execution, 'execution.json'), (input_path, input_name),
                         (args.reference_provenance, 'reference-provenance.json')):
        shutil.copyfile(source, evidence / name)
    result = {'schema_version': 1, 'case': case, 'assembler': args.assembler,
              'track': case.get('track', 'simulated'), 'preset': case.get('preset', 'quick'),
              'headline_eligible': bool(case.get('preset') == 'standard' and case.get('headline_eligible')
                                        and provenance.get('headline_eligible')),
              'execution': execution, 'sequence_outcome': None, 'replicons': [],
              'assessment': {'status': 'not_run', 'method': METHOD, 'completion_threshold': .99,
                             'identity_measurement_rule': 'Longest alignment span >100,000 bp or >one quarter of the original reference length.',
                             'structural_correctness': None,
                             'structural_correctness_note': 'Not measured by longest-alignment assessment.'},
              'provenance': {'reference_sha256': sha256(args.reference),
                             'execution_sha256': sha256(args.execution),
                             input_key: sha256(input_path),
                             'reference_provenance_sha256': sha256(args.reference_provenance),
                             'reference': provenance},
              'evidence_directory': evidence.name,
              'resources': {'assembler_wall_seconds': execution.get('elapsed_seconds'),
                            'assembler_process_tree_peak_rss_bytes': execution.get('process_tree_peak_rss_bytes'),
                            'memory_scope': 'Sampled sum of resident memory across the assembler process tree; shared pages may be counted more than once.'},
              'limitations': (['Quick is a workflow check, excluded from headline comparisons.']
                             if case.get('preset', 'quick') == 'quick' else
                             ['Initial whole-genome baseline validation, excluded from headline comparisons.']
                             if case.get('purpose') == 'baseline_validation' else [])}
    try:
        artifacts, workflow_graphs = retain_workflow_evidence(execution, args.execution.parent, evidence)
        result['provenance']['retained_workflow_files'] = artifacts
        result['provenance']['retained_graphs'] = retain_tool_evidence(execution, args.execution.parent, evidence) + workflow_graphs
        if execution.get('assembler') != args.assembler:
            raise ValueError('Execution assembler binding differs')
        if provenance.get('reference_sha256') != result['provenance']['reference_sha256']:
            raise ValueError('Reference-provenance/reference hash binding differs')
        if simulation.get('case') != case or simulation.get('status') != 'completed':
            raise ValueError('Input provenance/case binding differs or input preparation is incomplete')
        if simulation.get('reference_sha256') != result['provenance']['reference_sha256']:
            raise ValueError('Input/reference hash binding differs')
        if real:
            if (simulation.get('track') != 'real' or simulation.get('input_policy') != case.get('input_policy')
                    or simulation.get('sample_accession') != provenance.get('biosample')
                    or simulation.get('run_accession') != case.get('run_accession')
                    or simulation.get('reference_provenance_sha256') != sha256(args.reference_provenance)):
                raise ValueError('Real input/reference/run binding differs')
            result['limitations'].extend(['Modern comparison on full deposited ONT reads; not reproduction of the original paper subsets.',
                'Deposited references partly derive from tested assembler families; they are not independently established error-free truth.'])
        if case.get('preset') == 'standard':
            if provenance.get('mode') != 'whole_genome' or provenance.get('status') != 'admitted':
                raise ValueError('Standard assessment requires an admitted whole-genome reference')
            if simulation.get('reference_provenance_sha256') != sha256(args.reference_provenance):
                raise ValueError('Standard simulation/preparation provenance binding differs')
        if execution.get('reads_sha256') != simulation.get('reads_sha256') or not execution.get('reads_sha256'):
            raise ValueError('Execution/input read hash binding differs')
        if execution.get('status') == 'completed':
            if not args.assembly.is_file() or sha256(args.assembly) != execution.get('assembly_sha256'):
                raise ValueError('Final assembly differs from execution hash')
            references, queries = read_fasta(args.reference), read_fasta(args.assembly)
            if not references:
                raise ValueError('Reference has no records')
            shutil.copyfile(args.assembly, evidence / 'assembly.fasta')
            tripled = evidence / 'tripled-reference.fasta'
            tripled.write_text(''.join(f'>{name}\n{sequence * 3}\n' for name, sequence in references.items()))
            paf = evidence / 'alignment.paf'
            version = subprocess.run(['minimap2', '--version'], check=True, text=True, capture_output=True).stdout.strip()
            command = ['minimap2', '-c', '--cs=long', '-t', str(args.cpus), '-x', 'asm20',
                       '-r', '10000', '-g', '10000', '-z', '1000,500', str(tripled), str(args.assembly.resolve())]
            result['assessment'].update(command=command, mapper_version=version)
            measurement = measured_run(command, paf, evidence / 'minimap2.stderr.log', evidence)
            result['assessment']['mapper_measurement'] = measurement
            result['resources'].update(
                assessment_mapper_wall_seconds=measurement['elapsed_seconds'],
                assessment_mapper_process_tree_peak_rss_bytes=measurement['process_tree_peak_rss_bytes'])
            if measurement['exit_code'] != 0:
                raise ValueError('Mapper exited with non-zero status: ' + str(measurement['exit_code']))
            alignments = parse_paf(paf, references, queries)
            types = provenance.get('molecule_types', {})
            result['replicons'] = summarise(references, alignments, types)
            result['sequence_outcome'] = outcome(result['replicons'], len(queries))
            result['assessment'].update(status='completed', paf_sha256=sha256(paf), query_count=len(queries))
            result['provenance']['assembly_sha256'] = execution['assembly_sha256']
            if real:
                result['paper_assessment'] = assess_paper(args.reference, args.assembly, evidence, references, queries, types, args.cpus, version)
                paper_measurement = result['paper_assessment'].get('measurement', {})
                result['resources'].update(paper_mapper_wall_seconds=paper_measurement.get('elapsed_seconds'),
                    paper_mapper_process_tree_peak_rss_bytes=paper_measurement.get('process_tree_peak_rss_bytes'))

            # Reference is already identified by content hash; the transient tripled copy is unnecessary.
            tripled.unlink()
        elif execution.get('status') == 'software_error':
            result['assessment']['reason'] = 'Assembler failed; no sequence verdict is assigned.'
        else:
            raise ValueError('Execution is not a terminal software outcome: ' + str(execution.get('status')))
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        result['assessment'].update(status='error', error=f'{type(error).__name__}: {error}')
        result['sequence_outcome'] = None
        result['replicons'] = []
    elapsed = time.monotonic() - started
    result['resources']['assessment_wall_seconds'] = elapsed
    assembly_wall = execution.get('elapsed_seconds')
    result['resources']['workflow_wall_seconds'] = assembly_wall + elapsed if isinstance(assembly_wall, (int, float)) else None
    result['resources']['wall_time_scope'] = 'Assembler verification/execution plus exact assessment; excludes downloads, environment provisioning, simulation and scheduler waiting.'
    write_json(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('reference', 'assembly', 'execution', 'reference-provenance', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('--simulation', type=Path)
    input_group.add_argument('--input-provenance', type=Path)
    parser.add_argument('--case-json', required=True)
    parser.add_argument('--assembler', required=True)
    parser.add_argument('--cpus', type=int, default=1)
    args = parser.parse_args()
    if args.cpus < 1:
        parser.error('--cpus must be positive')
    assess(args)


if __name__ == '__main__':
    main()
