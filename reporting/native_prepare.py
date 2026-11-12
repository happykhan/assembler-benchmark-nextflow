"""Prepare presentation metadata from retained outputs, never run an assessor.

Parsing GFA and saved PAF is export work. Website rendering consumes only these
sealed metadata files; it cannot open assembly sequences or run alignment.
"""
import csv
from html import escape
import json
from pathlib import Path
from .common import digest, save
from .graph_artifacts import parse_gfa


def prepare_presentation(root, records):
    root = Path(root)
    prepared = []
    for number, record in enumerate(records):
        case, assembler = record['case']['id'], record['assembler']
        evidence = root / record['evidence_directory']
        assemblies = root / 'assemblies' / case / assembler
        section = {'case_id': case, 'assembler': assembler, 'graphs': [], 'alignments': None}
        for graph_source in sorted(assemblies.glob('*.gfa')):
            graph = parse_gfa(graph_source)
            retained = next((g for g in record.get('provenance', {}).get('retained_graphs', []) if g.get('file') == graph_source.name), {})
            graph['source']['role'] = retained.get('role', 'unclassified_output')
            model = {'schema_version': 1, 'graph': graph,
                'assembly_sha256': record['provenance'].get('assembly_sha256'),
                'availability': {'status': graph['status'], 'title': 'Recorded assembly graph',
                    'description': 'Saved GFA topology only. Reference origins and physical topology are not inferred.'},
                'reference_origins': {'references': [], 'nodes': {}, 'node_intervals': {},
                    'unassigned_reason': 'No validated graph-to-reference association was recorded.'}}
            relative = f'presentation/graphs/{number}-{graph_source.stem}.json'
            save(root / relative, model)
            section['graphs'].append({'file': relative, 'source_sha256': digest(graph_source)})
        paf = evidence / 'alignment.paf'
        binding = record.get('assessment', {}).get('paf_sha256') or record.get('diagnostics', {}).get('paf_sha256')
        if paf.is_file() and binding and digest(paf) == binding:
            rows = []
            with paf.open() as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    f = line.rstrip('\n').split('\t')
                    if len(f) < 12:
                        raise ValueError('Invalid saved PAF: ' + str(paf))
                    qlen, qs, qe, rlen, rs, re = map(int, (f[1], f[2], f[3], f[6], f[7], f[8]))
                    if not 0 <= qs < qe <= qlen or not 0 <= rs < re <= rlen or f[4] not in ('+', '-'):
                        raise ValueError('Invalid saved PAF coordinate interval')
                    rows.append([f[0], qlen, qs, qe, f[4], f[5], rlen, rs, re, f[9], f[10], f[11]])
            relative = f'presentation/alignments/{number}.tsv'
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('w', newline='') as stream:
                writer = csv.writer(stream, delimiter='\t')
                writer.writerow(['query', 'query_length', 'query_start', 'query_end', 'strand', 'reference', 'reference_length', 'reference_start', 'reference_end', 'matches', 'block_length', 'mapq'])
                writer.writerows(rows)
            svg = f'presentation/alignments/{number}.svg'
            (root / svg).write_text(coordinate_svg(rows))
            section['alignments'] = {'coordinates': relative, 'figure': svg, 'paf_sha256': binding,
                'coordinate_system': 'Recorded mapper coordinates, 0-based half-open; tripled references remain tripled. No origin inference.'}
        prepared.append(section)
    save(root / 'presentation/index.json', {'schema_version': 1, 'results': prepared})


def coordinate_svg(rows):
    pairs = sorted({(r[5], r[0]) for r in rows})
    if not pairs:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="800" height="100"><text x="20" y="40">No alignment records in the saved PAF; sequence absence is not established.</text></svg>'
    width, height = 800, 80 + 220 * len(pairs)
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" role="img" aria-label="Saved alignment coordinates"><rect width="100%" height="100%" fill="white"/><g font-family="sans-serif" font-size="13" fill="#20242a"><text x="20" y="25">Saved mapper coordinates · reference on x; query on y · no new alignment</text>']
    for index, (reference, query) in enumerate(pairs):
        selected = [r for r in rows if r[5] == reference and r[0] == query]
        y = 70 + index * 220
        qlen, rlen = selected[0][1], selected[0][6]
        parts.append(f'<text x="70" y="{y-12}">{escape(reference)} ({rlen:,} bp recorded reference) / {escape(query)} ({qlen:,} bp)</text><path d="M70 {y} v160 h660" fill="none" stroke="#777"/>')
        for r in selected:
            qstart, qend = (r[2], r[3]) if r[4] == '+' else (r[3], r[2])
            parts.append(f'<line x1="{70+660*r[7]/rlen:.3f}" y1="{y+160-160*qstart/qlen:.3f}" x2="{70+660*r[8]/rlen:.3f}" y2="{y+160-160*qend/qlen:.3f}" stroke="#326eae" stroke-width="2"/>')
        parts.append(f'<text x="70" y="{y+180}">0</text><text x="650" y="{y+180}">{rlen:,} bp</text>')
    return ''.join(parts) + '</g></svg>'
