"""Optional measured mapping evidence; never a replacement for exact scores."""
from pathlib import Path
import shutil
import subprocess
from benchlib.process import measured_run
from .common import digest,fasta
from .diagnostics import minimap2_command,summarise_paf


def measure_diagnostics(case,reference,assembly,evidence,cpus=1,paf=None,run_mapping=False):
    evidence=Path(evidence)
    result={'status':'not_measured','method':'paf-recovery-evidence-v1',
            'reference_sha256':digest(reference),'assembly_sha256':digest(assembly),
            'scope':'Supplementary evidence only; unavailable measurement never establishes sequence absence.'}
    if paf is None and not run_mapping:
        return result
    measurement=None
    try:
        target=evidence/'alignment.paf'
        if paf is not None:
            if Path(paf).resolve()!=target.resolve():
                shutil.copyfile(paf,target)
            result['source']='Saved PAF supplied by caller'
        else:
            result['mapper_version']=subprocess.run(['minimap2','--version'],check=True,text=True,capture_output=True,timeout=30).stdout.strip()
            command=minimap2_command(Path(reference).resolve(),Path(assembly).resolve(),cpus)
            result['command']=command
            measurement=measured_run(command,target,evidence/'minimap2.stderr.log',evidence)
            result['measurement']=measurement
            if measurement['exit_code']!=0:
                raise ValueError('Diagnostic mapper exited with non-zero status: '+str(measurement['exit_code']))
        result.update(summarise_paf(case,target,{k:len(v) for k,v in fasta(assembly).items()}))
        result.update(status='completed',paf_sha256=digest(target))
        if digest(reference)!=result['reference_sha256'] or digest(assembly)!=result['assembly_sha256']:
            raise ValueError('Mapping input sequences changed during measurement')
    except (ValueError,OSError,KeyError,subprocess.SubprocessError) as error:
        # Retain partial PAF/logs and execution timing, but no interpreted metrics.
        result={key:value for key,value in result.items() if key not in ('replicons','candidate_joins')}
        result.update(status='error',error=f'{type(error).__name__}: {error}')
        partial=evidence/'alignment.paf'
        if partial.is_file():
            result['partial_paf_sha256']=digest(partial)
    return result
