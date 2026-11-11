#!/usr/bin/env python3
"""Independent exact placement; saved reads, assemblies and scores are read-only."""
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / 'evidence/standard-runs/standard-baseline-v1/bundle'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fasta(text):
    records, name = {}, None
    for line in text.splitlines():
        if line.startswith('>'):
            name = line[1:].split()[0]
            if name in records:
                raise ValueError('Duplicate sequence ID')
            records[name] = ''
        elif line.strip():
            if name is None:
                raise ValueError('Sequence before header')
            records[name] += line.strip().upper()
    return records


def rc(sequence):
    return sequence.translate(str.maketrans('ACGT', 'TGCA'))[::-1]


def intervals(start, length, size):
    if length > size:
        raise ValueError('Audit requires contigs no longer than the reference')
    end = start + length
    return [(start, min(end, size))] + ([(0, end-size)] if end > size else [])


def coverage(placed, size):
    events = {0: 0, size: 0}
    for start, stop in placed:
        events[start] = events.get(start, 0) + 1
        events[stop] = events.get(stop, 0) - 1
    depth, previous, histogram, gaps = 0, 0, {}, []
    for position, delta in sorted(events.items()):
        if position > previous:
            histogram[depth] = histogram.get(depth, 0) + position-previous
            if depth == 0:
                gaps.append({'start_0based': previous, 'end_0based_exclusive': position,
                             'length_bp': position-previous})
        depth += delta
        previous = position
    assert depth == 0
    return {'covered_bp': size-histogram.get(0, 0),
            'coverage_fraction': (size-histogram.get(0, 0))/size,
            'depth_histogram_bp': histogram, 'gaps': gaps,
            'overlap_excess_bp': sum(max(d-1, 0)*n for d,n in histogram.items())}


def n50(lengths):
    cumulative = 0
    for length in sorted(lengths, reverse=True):
        cumulative += length
        if cumulative*2 >= sum(lengths):
            return length


def placements(sequence, reference):
    starts = {}
    doubled = reference*2
    for strand, query in [('+', sequence), ('-', rc(sequence))]:
        offset = 0
        while True:
            position = doubled.find(query, offset)
            if position < 0 or position >= len(reference):
                break
            starts.setdefault(position, []).append(strand)
            offset = position+1
    return [{'start_0based': start, 'strands': strands,
             'reference_intervals': intervals(start, len(sequence), len(reference))}
            for start, strands in sorted(starts.items())]


def main():
    registry_path = ROOT/'assets/references.json'
    registry = {r['id']:r for r in json.loads(registry_path.read_text())['references']}
    data = json.loads((BUNDLE/'results.json').read_text())['results']
    output = {'schema_version':1, 'method':'Direct exact string matching to both orientations of doubled native circular references; no aligner or pipeline PAF parser used',
              'source_results_sha256':sha(BUNDLE/'results.json'),
              'reference_registry_sha256':sha(registry_path), 'results':[]}
    for result in data:
        case = result['case']
        reference_id = case['reference_id']
        definition = registry[reference_id]
        archive = ROOT/'references'/(reference_id+'.source.gz')
        assert sha(archive) == definition['download_sha256']
        references = fasta(gzip.decompress(archive.read_bytes()).decode())
        assert len(references) == 1
        accession, reference = next(iter(references.items()))
        molecule = definition['molecules'][0]
        assert accession == molecule['accession']
        assert hashlib.sha256(reference.encode()).hexdigest() == molecule['sequence_sha256']
        assembly_path = BUNDLE/'assemblies'/case['id']/result['assembler']/'assembly.fasta'
        assert sha(assembly_path) == result['provenance']['assembly_sha256']
        assembly = fasta(assembly_path.read_text())
        unique, possible, contigs = [], [], []
        for name, sequence in assembly.items():
            matches = placements(sequence, reference)
            for match in matches:
                possible.extend(match['reference_intervals'])
            if len(matches) == 1:
                unique.extend(matches[0]['reference_intervals'])
            contigs.append({'id':name, 'length_bp':len(sequence),
                            'sequence_sha256':hashlib.sha256(sequence.encode()).hexdigest(),
                            'exact_placement_count':len(matches), 'placements':matches})
        lengths = [len(s) for s in assembly.values()]
        existing = result['replicons'][0]
        row = {'case_id':case['id'], 'assembler':result['assembler'], 'reference_id':reference_id,
               'reference_accession':accession, 'reference_length_bp':len(reference),
               'reference_sequence_sha256':molecule['sequence_sha256'], 'assembly_sha256':sha(assembly_path),
               'contig_count':len(assembly), 'assembly_total_bp':sum(lengths),
               'longest_contig_bp':max(lengths), 'n50_bp':n50(lengths),
               'longest_contig_reference_fraction':max(lengths)/len(reference),
               'all_contigs_exact_substrings':all(c['exact_placement_count']>0 for c in contigs),
               'all_contigs_unambiguously_placed':all(c['exact_placement_count']==1 for c in contigs),
               'unique_placement_coverage':coverage(unique,len(reference)),
               'possible_placement_coverage_upper_bound':coverage(possible,len(reference)),
               'existing_assessment_longest_alignment_bp':existing['longest_alignment_span_bp'],
               'existing_contiguity':existing['contiguity'],
               'existing_sequence_outcome':result['sequence_outcome'],
               'longest_contig_equals_reported_alignment_span':max(lengths)==existing['longest_alignment_span_bp'],
               'can_any_contig_meet_99_percent_length':max(lengths)/len(reference)>=.99,
               'contigs':contigs}
        output['results'].append(row)
    Path(__file__).with_name('exact-placement.json').write_text(json.dumps(output,indent=2)+'\n')
    for r in output['results']:
        print(r['case_id'],r['assembler'],r['contig_count'],r['all_contigs_exact_substrings'],
              r['all_contigs_unambiguously_placed'],r['unique_placement_coverage']['coverage_fraction'],
              r['unique_placement_coverage']['gaps'])


if __name__ == '__main__':
    main()
