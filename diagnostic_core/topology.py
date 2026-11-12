"""Associate tool labels with output sequences without consulting truth references."""
from collections import defaultdict
from pathlib import Path
import hashlib
import shutil
from .common import digest,fasta,reverse_complement
from .topology_metadata import parse_flye_assembly_info,parse_plassembler_summary


def _sequence_key(sequence):
    return len(sequence),hashlib.sha256(min(sequence,reverse_complement(sequence)).encode()).hexdigest()


def output_topology(directory,execution,assembly,evidence):
    directory=Path(directory);evidence=Path(evidence)
    final=fasta(assembly);labels={};sources=[];inherited=[]
    names={(r['source_role'],r['source_contig_id']):r['contig_id'] for r in execution.get('contig_sources',[])}
    tool=execution.get('tool')
    path=directory/'tool-output/assembly_info.txt' if tool in ('flye','flye-meta') else directory/'tool-output/benchmark_summary.tsv'
    parser=parse_flye_assembly_info if tool in ('flye','flye-meta') else parse_plassembler_summary
    if tool not in ('flye','flye-meta','plassembler'):
        return {},{'sources':[],'inherited_chromosome_claims':[],
                   'scope':'No supported tool circularity metadata; end-sensitive comparison remains available.'}
    metadata=parser(path)
    if metadata['status']=='available':
        shutil.copyfile(path,evidence/('final-'+path.name))
        sources.append(metadata['source'])
        for row in metadata['contigs']:
            name=names.get(('final_plasmids',row['id']),row['id']) if tool=='plassembler' else row['id']
            claim=row['reported_circularity']
            if name in final and len(final[name])==row['length_bp'] and claim in ('circular','not_circular'):
                labels[name]=claim=='circular'
    if tool=='plassembler':
        initial=directory/'tool-output/flye_output/assembly.fasta'
        info=directory/'tool-output/flye_output/assembly_info.txt'
        chromosome=directory/'tool-output/chromosome.fasta'
        if initial.is_file() and info.is_file() and chromosome.is_file() and digest(chromosome)==execution.get('retained_chromosome_sha256'):
            before=digest(initial);metadata=parse_flye_assembly_info(info)
            if metadata['status']=='available':
                shutil.copyfile(info,evidence/'initial-flye-assembly_info.txt')
                sources.append(metadata['source'])
                claims={r['id']:r for r in metadata['contigs']}
                candidates=defaultdict(list)
                for name,sequence in fasta(initial).items():
                    row=claims.get(name,{})
                    claim=row.get('reported_circularity') if row.get('length_bp')==len(sequence) else None
                    candidates[_sequence_key(sequence)].append((name,claim))
                for name,sequence in fasta(chromosome).items():
                    matched=candidates[_sequence_key(sequence)]
                    values={r[1] for r in matched}
                    normalized=names.get(('retained_chromosome',name),name)
                    if normalized in final and final[normalized]==sequence and len(values)==1 and values<={'circular','not_circular'}:
                        claim=next(iter(values));labels[normalized]=claim=='circular'
                        inherited.append({'retained_contig':normalized,'initial_contigs':[r[0] for r in matched],
                            'reported_circularity':claim,'initial_assembly_sha256':before,
                            'sequence_sha256':_sequence_key(sequence)[1],
                            'association':'Exact complete sequence, allowing reverse complement only; no truth reference consulted.'})
            if digest(initial)!=before:
                raise ValueError('Initial Flye output changed while associating chromosome claims')
    return labels,{'sources':sources,'inherited_chromosome_claims':inherited,
                   'scope':'Tool-reported circularity only, not physical topology or reference recovery.'}
