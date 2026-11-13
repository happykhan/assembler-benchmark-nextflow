"""Typed assembler execution, independent of assessment and presentation."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

from .adapters import ADAPTERS, environment_versions
from .assessment import read_fasta
from .io import digest
from .process import measured_run
from .workflow_options import workflow_options


def save(path,value):
    Path(path).write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')


def assemble(prepared, workflow, directory, project):
    prepared=Path(prepared).resolve();directory=Path(directory).resolve();project=Path(project).resolve()
    directory.mkdir(parents=True)
    started=time.monotonic();record={'schema_version':2,'status':'execution_failure','workflow':workflow,
        'automatic_retries':0,'failure_kind':'infrastructure','assembly':None,'graph':None,'exit_code':None}
    try:
        inputs=json.loads((prepared/'input.json').read_text())
        for file,checksum in inputs['file_sha256'].items():
            if digest(prepared/file)!=checksum:raise ValueError('Prepared input changed: '+file)
        expected_layout='short_paired' if workflow['tool']=='skesa' else 'long_single'
        if inputs['layout']!=expected_layout:raise ValueError('Workflow/read layout is not applicable')
        record['input_id']=inputs['id'];record['input_sha256']=digest(prepared/'input.json')
        record['read_sha256']={f:digest(prepared/f) for f in inputs['files']}
        reads=[]
        for name in inputs['files']:
            relative=Path('..')/prepared.name/name
            reads.append(str(relative) if (directory/relative).is_file() else str(prepared/name))
        tool=workflow['tool'];cpus=workflow['resources']['cpus'];options=workflow_options(tool,workflow.get('configuration',{}))
        executable='skesa' if tool=='skesa' else ADAPTERS[workflow['adapter']].executable
        version=subprocess.check_output([executable,'-V' if tool=='miniasm' else '--version'],text=True,stderr=subprocess.STDOUT,timeout=30).strip()
        if not re.search(r'(?<![0-9.])'+re.escape(workflow['version'])+r'(?![0-9.])',version):
            raise ValueError('Actual assembler version differs from declared version: '+version)
        record['actual_version']=workflow['version'];record['version_output']=version
        if tool=='skesa':
            command=['skesa','--reads',','.join(reads),'--cores',str(cpus),'--memory',str(workflow['resources']['memory_gb']),'--contigs_out','contigs.fasta']
            source=directory/'contigs.fasta';graph=None
        else:
            adapter=ADAPTERS[workflow['adapter']];command=adapter.command(reads[0],cpus,options)
            source=directory/adapter.assembly_relative;graph=directory/adapter.graph_relative
            if tool in ('miniasm','miniasm-plus'):
                command=['python',str(project/'bin/run-miniasm.py'),'--reads',reads[0],'--output','tool-output','--threads',str(cpus),
                    '--expected-versions-json',json.dumps(environment_versions(workflow,project),sort_keys=True)]
                if tool=='miniasm-plus':command.append('--polish')
        record['command']=[s.replace(str(project),'pipeline').replace(str(prepared),'prepared') for s in command]
        measurement=measured_run(command,directory/'stdout.log',directory/'stderr.log',directory)
        record.update(measurement)
        if measurement['exit_code']:
            record['reason']='Assembler returned a non-zero exit status';record['failure_kind']='software'
        elif not source.is_file():
            record['reason']='Assembler did not produce its declared final FASTA';record['failure_kind']='software'
        else:
            output=directory/'assembly.fasta'
            if tool=='plassembler':
                sources=[('final_plasmids',source)];chromosome=directory/'tool-output/chromosome.fasta'
                if chromosome.is_file():sources.append(('retained_chromosome',chromosome))
                with output.open('w') as stream:
                    for role,path in sources:
                        for name,sequence in read_fasta(path).items():stream.write('>'+role+':'+name+'\n'+sequence+'\n')
                record['assembly_scope']='Actual final plasmids plus retained chromosome'
                final_graph=directory/'tool-output/benchmark_plasmids.gfa'
                if final_graph.is_file():graph=final_graph;record['graph_scope']='Final plasmids only'
            else:shutil.copyfile(source,output)
            if output.stat().st_size:read_fasta(output)
            record.update(status='completed',failure_kind=None,assembly='assembly.fasta',assembly_sha256=digest(output))
            if graph is not None and graph.is_file():
                if graph!=directory/'assembly.gfa':shutil.copyfile(graph,directory/'assembly.gfa')
                record.update(graph='assembly.gfa',graph_sha256=digest(directory/'assembly.gfa'))
    except Exception as error:
        record['reason']=(type(error).__name__+': '+str(error)).replace(str(prepared),'prepared').replace(str(project),'pipeline').replace(str(directory),'execution')
    record['wall_seconds']=time.monotonic()-started
    record['wall_scope']='Verification, version check, assembly and output validation; preparation and scheduler waiting excluded.'
    save(directory/'execution.json',record)
    return record
