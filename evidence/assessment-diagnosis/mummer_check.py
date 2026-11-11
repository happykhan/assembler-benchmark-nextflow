#!/usr/bin/env python3
"""Independent NUCmer checks of saved assemblies; no assembly or simulation."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path('/well/aanensen/users/rva470/assembler-benchmark-nextflow')
OUTPUT = ROOT/'evidence/assessment-diagnosis/mummer'
BIN = Path('/well/aanensen/users/rva470/.cache/rattler/cached-envs-v0/mummer4-2eeacd5d28a50228/bin')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fasta(text):
    rows, name = {}, None
    for line in text.splitlines():
        if line.startswith('>'):
            name = line[1:].split()[0]
            rows[name] = []
        elif line.strip():
            rows[name].append(line.strip())
    return {name:''.join(parts) for name,parts in rows.items()}


def merge(rows):
    output = []
    for start,end in sorted(rows):
        if output and start <= output[-1][1]:
            output[-1][1] = max(output[-1][1],end)
        else:
            output.append([start,end])
    return output


def modulo_interval(start, end, size):
    rows = []
    while start < end:
        offset = start%size
        length = min(end-start,size-offset)
        rows.append([offset,offset+length])
        start += length
    return rows


def main():
    OUTPUT.mkdir(parents=True,exist_ok=True)
    registry = {r['id']:r for r in json.loads((ROOT/'assets/references.json').read_text())['references']}
    bundle = ROOT/'results/standard-baseline-v1/bundle'
    results = json.loads((bundle/'results.json').read_text())['results']
    evidence = {'method':'Independent NUCmer4 alignments; single-copy unique-reference anchors and doubled-reference maxmatch; best-query delta filtering; coordinates modulo native reference length',
                'nucmer_version':subprocess.check_output([str(BIN/'nucmer'),'--version'],text=True).strip(),
                'nucmer_binary_sha256':sha(BIN/'nucmer'),'source_results_sha256':sha(bundle/'results.json'),'results':[]}
    for result in results:
        case = result['case']
        definition = registry[case['reference_id']]
        archive = ROOT/'references'/(case['reference_id']+'.source.gz')
        assert sha(archive)==definition['download_sha256']
        reference = next(iter(fasta(gzip.decompress(archive.read_bytes()).decode()).values()))
        size = len(reference)
        assembly = bundle/'assemblies'/case['id']/result['assembler']/'assembly.fasta'
        assert sha(assembly)==result['provenance']['assembly_sha256']
        row = {'case_id':case['id'],'assembler':result['assembler'],'reference_length_bp':size,
               'assembly_sha256':sha(assembly),'checks':[]}
        for copies in (1,2):
            directory = OUTPUT/case['id']/result['assembler']/str(copies)
            directory.mkdir(parents=True,exist_ok=True)
            reference_path = directory/'reference.fasta'
            reference_path.write_text('>reference\n'+reference*copies+'\n')
            prefix = directory/'alignment'
            command = [str(BIN/'nucmer')]
            if copies==2:
                command.append('--maxmatch')
            command += ['-p',str(prefix),str(reference_path),str(assembly)]
            with (directory/'nucmer.stderr.log').open('w') as stderr:
                subprocess.run(command,check=True,stderr=stderr)
            filtered = directory/'query-best.delta'
            with filtered.open('w') as stream:
                subprocess.run([str(BIN/'delta-filter'),'-q',str(prefix)+'.delta'],stdout=stream,check=True)
            coordinates = directory/'coordinates.tsv'
            with coordinates.open('w') as stream:
                subprocess.run([str(BIN/'show-coords'),'-T','-H','-r','-l','-c',str(filtered)],stdout=stream,check=True)
            blocks,reference_intervals = [],[]
            for line in coordinates.read_text().splitlines():
                fields = line.split()
                assert len(fields)==13,fields
                rs,re,qs,qe,rl,ql = map(int,fields[:6])
                pieces = modulo_interval(min(rs,re)-1,max(rs,re),size)
                reference_intervals.extend(pieces)
                blocks.append({'reference_interval_1based_inclusive':[rs,re],
                               'query_interval_1based_inclusive':[qs,qe],
                               'reference_span_bp':rl,'query_span_bp':ql,
                               'identity_percent':float(fields[6]),'query':fields[12],
                               'modulo_reference_intervals':pieces})
            covered = merge(reference_intervals)
            gaps = []
            cursor = 0
            for start,end in covered:
                if start>cursor:gaps.append([cursor,start])
                cursor=end
            if cursor<size:gaps.append([cursor,size])
            row['checks'].append({'reference_copies':copies,'command':command,'blocks':blocks,
                                   'coverage_intervals':covered,'reference_covered_bp':sum(e-s for s,e in covered),
                                   'reference_coverage_fraction':sum(e-s for s,e in covered)/size,
                                   'uncovered_intervals':gaps,'coordinates_sha256':sha(coordinates),
                                   'delta_sha256':sha(Path(str(prefix)+'.delta'))})
        evidence['results'].append(row)
    (OUTPUT/'summary.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps({r['case_id']+'/'+r['assembler']:[c['reference_coverage_fraction'] for c in r['checks']] for r in evidence['results']},indent=2))


if __name__=='__main__':
    main()
