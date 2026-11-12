"""Diagnostic exact-copy assessment and independent agreement evidence."""
from benchlib.evidence import retain_workflow_evidence
from pathlib import Path
import time
import shutil
import hashlib
from .common import digest, fasta, load, save
from .preparation import scientific_case
from .scoring import evaluate
from .determinism import sequence_signature, biological_signature
from .read_order import sequence_fingerprint
from .assessments import continuous_assessment
from .diagnostics import summarise_paf
from .tolerant import evaluate_tolerant
from .topology import output_topology
from .plassembler_outputs import endpoint_output
from .mapping import measure_diagnostics

METHOD = 'exact-dedicated-molecule-v1'


def assess(meta, reference, reference_provenance, input_provenance, assembly, execution_path,
           assembler, output, paf=None, circularity=None, run_mapping=False, cpus=1):
    """Failed execution or measurement never supplies a negative sequence result."""
    started=time.monotonic()
    output=Path(output)
    evidence=output.with_name(output.stem+'.evidence')
    evidence.mkdir(parents=True,exist_ok=False)
    for source,name in ((execution_path,'execution.json'),(input_provenance,'input-provenance.json'),
                        (reference_provenance,'reference-provenance.json')):
        shutil.copyfile(source,evidence/name)
    case=scientific_case(meta)
    execution=load(execution_path)
    prepared=load(input_provenance)
    provenance=load(reference_provenance)
    result={'schema_version':1,'case':meta,'assembler':assembler,'track':'diagnostic',
            'preset':meta.get('preset','standard'),'headline_eligible':False,
            'execution':execution,'sequence_outcome':None,'replicons':[],
            'evidence_directory':evidence.name,
            'assessment':{'status':'not_run','method':METHOD,'structural_correctness':None,
                'endpoint':'Dedicated exact-copy molecules; circular sequences allow rotation and strand; linear sequences allow strand only.'},
            'provenance':{'reference_sha256':digest(reference),'execution_sha256':digest(execution_path),
                'input_provenance_sha256':digest(input_provenance),
                'reference_provenance_sha256':digest(reference_provenance),'reference':provenance},
            'resources':{'assembler_wall_seconds':execution.get('elapsed_seconds'),
                'assembler_process_tree_peak_rss_bytes':execution.get('process_tree_peak_rss_bytes')},
            'limitations':['Diagnostic exact-copy endpoint; distinct from Wick longest-alignment completion. Physical topology is not inferred from sequence recovery.']}
    try:
        graphs=[]
        directory=Path(execution_path).parent
        for name in ('stdout.log','stderr.log'):
            source=directory/name
            if source.is_file():
                if execution.get('log_sha256',{}).get(name) and digest(source)!=execution['log_sha256'][name]:
                    raise ValueError('Execution log checksum differs: '+name)
                shutil.copyfile(source,evidence/name)
        declared=execution.get('graph_path')
        if declared and (Path(declared).name!=declared or Path(declared).suffix!='.gfa'):
            raise ValueError('Declared graph must be a sibling GFA file')
        if declared and not (directory/declared).is_file():
            raise ValueError('Declared graph is missing')
        for graph in sorted(directory.glob('*.gfa')):
            checksum=digest(graph)
            if graph.name==declared and checksum!=execution.get('graph_sha256'):
                raise ValueError('Declared graph checksum differs')
            shutil.copyfile(graph,evidence/graph.name)
            graphs.append({'file':graph.name,'sha256':checksum,'role':'final_graph' if graph.name==declared and execution.get('status')=='completed' else 'partial_or_diagnostic_graph'})
        artifacts,workflow_graphs=retain_workflow_evidence(execution,directory,evidence)
        result['provenance']['retained_workflow_files']=artifacts
        result['provenance']['retained_graphs']=graphs+workflow_graphs
        if prepared.get('status')!='completed' or prepared.get('case')!=meta or prepared.get('diagnostic_case')!=case:
            raise ValueError('Prepared diagnostic input/case binding differs')
        if prepared.get('reference_sha256')!=digest(reference) or provenance.get('reference_sha256')!=digest(reference):
            raise ValueError('Diagnostic reference hash binding differs')
        if prepared.get('reference_provenance_sha256')!=digest(reference_provenance):
            raise ValueError('Reference provenance receipt binding differs')
        if execution.get('assembler')!=assembler or not execution.get('reads_sha256') or execution['reads_sha256']!=prepared.get('reads_sha256'):
            raise ValueError('Execution/input/assembler binding differs')
        sequences=fasta(reference)
        if set(sequences)!={r['refseq_accession'] for r in case['replicons']} or any(len(sequences[r['refseq_accession']])!=r['length_bp'] for r in case['replicons']):
            raise ValueError('Truth reference inventory differs from case')
        if execution.get('status')=='completed':
            if digest(assembly)!=execution.get('assembly_sha256'):
                raise ValueError('Assembly changed after execution')
            shutil.copyfile(assembly,evidence/'assembly.fasta')
            endpoint_assembly=assembly
            plasmid_only=execution.get('tool')=='plassembler'
            if plasmid_only:
                plasmids,chromosome=endpoint_output(directory,execution,assembly,
                    meta.get('assembler_options',{}).get('plassembler_no_chromosome',False))
                if chromosome is not None:
                    shutil.copyfile(chromosome,evidence/'retained-chromosome.fasta')
                endpoint_assembly=plasmids
                shutil.copyfile(plasmids,evidence/'final-plasmids.fasta')
                result['provenance']['diagnostic_endpoint_assembly_sha256']=digest(plasmids)
                result['assessment']['output_scope']='Strict endpoint uses actual final plasmids; whole-workflow output signatures include retained chromosome.'
            strict=evaluate(case,reference,endpoint_assembly,plasmid_only)
            result['evaluation']=strict
            result['replicons']=strict['replicons']
            result['sequence_outcome']=strict['status']
            result['assessment'].update(status='completed',query_count=strict['contig_count'])
            result['provenance']['assembly_sha256']=digest(assembly)
            if circularity is None:
                circularity,topology_evidence=output_topology(directory,execution,assembly,evidence)
                result['provenance']['output_topology']=topology_evidence
            result['signatures']={'byte_sha256':digest(endpoint_assembly),
                'whole_workflow_byte_sha256':digest(assembly),
                'truth_anchored':sequence_signature(case,reference,endpoint_assembly),
                'biological_sha256':biological_signature(strict),
                'reference_independent':sequence_fingerprint(fasta(assembly).items(),circularity)}
            if case['category']=='S7':
                result['read_order_input']=prepared['read_order']
                result['secondary_reference_status']=strict['status']
                result['assessment']['primary_endpoint']='Output agreement across read orders/repeats, independent of the secondary reference verdict.'
            mode=meta.get('supplementary_assessor_id')
            if mode=='continuous-evidence-v1' or case['category']=='S6':
                result['tolerant_assessment']=continuous_assessment(case)
            elif mode=='small-plasmid-tolerant-v1':
                result['tolerant_assessment']=evaluate_tolerant(case,reference,assembly)
            result['diagnostics']=measure_diagnostics(case,reference,assembly,evidence,cpus,paf,run_mapping)
            mapping=result['diagnostics'].get('measurement',{})
            result['resources'].update(assessment_mapper_wall_seconds=mapping.get('elapsed_seconds'),
                assessment_mapper_process_tree_peak_rss_bytes=mapping.get('process_tree_peak_rss_bytes'))
        elif execution.get('status') in ('software_error','resource_error'):
            result['assessment']['reason']='Assembler execution failed; no sequence outcome is assigned.'
        else:
            raise ValueError('Execution is not a terminal software outcome: '+str(execution.get('status')))
    except (ValueError,OSError,KeyError) as error:
        result['assessment'].update(status='error',error=f'{type(error).__name__}: {error}')
        result['sequence_outcome']=None
        result['replicons']=[]
        result.pop('evaluation',None)
        result.pop('signatures',None)
    elapsed=time.monotonic()-started
    result['resources'].update(assessment_wall_seconds=elapsed,
        workflow_wall_seconds=execution['elapsed_seconds']+elapsed if isinstance(execution.get('elapsed_seconds'),(int,float)) else None,
        wall_time_scope='Assembler verification/execution plus diagnostic exact assessment; excludes preparation, downloads and scheduler waiting.')
    save(output,result)
    return result
