"""Verify final Plassembler constituent roles before strict or whole-output scoring."""
from pathlib import Path
import hashlib
from .common import digest,fasta


def endpoint_output(directory,execution,assembly,no_chromosome=False):
    directory=Path(directory)
    declared=execution.get('assembly_sources')
    if declared is not None:
        sources={};normal={};mapping=[]
        if not isinstance(declared,list):
            raise ValueError('Plassembler assembly sources must be a list')
        for row in declared:
            role=row.get('role')
            if role not in ('final_plasmids','retained_chromosome') or role in sources:
                raise ValueError('Plassembler constituent roles are unknown or duplicated')
            relative=Path(row['file']);path=directory/relative
            if relative.is_absolute() or '..' in relative.parts or path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()):
                raise ValueError('Unsafe Plassembler constituent source path')
            if digest(path)!=row.get('sha256') or row.get('bytes',path.stat().st_size)!=path.stat().st_size:
                raise ValueError('Plassembler constituent source hash/size differs')
            sources[role]=path
            for name,sequence in fasta(path).items():
                identifier=role+':'+name
                normal[identifier]=sequence
                mapping.append({'contig_id':identifier,'source_role':role,'source_contig_id':name})
        if 'final_plasmids' not in sources:
            raise ValueError('Plassembler final plasmid constituent is missing')
        if no_chromosome and 'retained_chromosome' in sources:
            raise ValueError('Unexpected chromosome in explicit no-chromosome workflow')
        if not no_chromosome and 'retained_chromosome' not in sources:
            raise ValueError('Plassembler retained chromosome constituent is missing')
        if 'retained_chromosome' in sources and digest(sources['retained_chromosome'])!=execution.get('retained_chromosome_sha256'):
            raise ValueError('Retained chromosome source binding differs')
        observed=execution.get('contig_sources')
        if not isinstance(observed,list) or len(observed)!=len(mapping) or len({r.get('contig_id') for r in observed})!=len(observed):
            raise ValueError('Plassembler normalized contig mapping is missing or duplicated')
        if sorted(observed,key=lambda r:r['contig_id'])!=sorted(mapping,key=lambda r:r['contig_id']) or fasta(assembly)!=normal:
            raise ValueError('Plassembler normalized assembly differs from constituent role/sequence mapping')
        return sources['final_plasmids'],sources.get('retained_chromosome')
    # Read-only compatibility with the earlier native result encoding.
    plasmids=directory/'tool-output/benchmark_plasmids.fasta'
    chromosome=directory/'tool-output/chromosome.fasta'
    if not plasmids.is_file():
        raise ValueError('Plassembler dedicated-plasmid output is missing')
    combined=plasmids.read_bytes()
    if not no_chromosome:
        if not chromosome.is_file() or digest(chromosome)!=execution.get('retained_chromosome_sha256'):
            raise ValueError('Plassembler retained chromosome is missing or unverified')
        combined+=(b'\n' if combined else b'')+chromosome.read_bytes()
    if hashlib.sha256(combined).hexdigest()!=execution['assembly_sha256']:
        raise ValueError('Plassembler final plasmid/chromosome roles differ from execution')
    return plasmids,None if no_chromosome else chromosome
