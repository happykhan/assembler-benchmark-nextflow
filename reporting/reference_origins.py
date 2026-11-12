"""Display associations from exact-contig results, GFA paths and recorded identity hashes.

No sequence alignment, new scoring or within-segment coordinate inference.
"""
import csv
import hashlib
from functools import lru_cache
from .common import ROOT
CHROMOSOME = ('#72a9e8', '#326eae')
PLASMIDS = [('#d8974e', '#9c5a15'), ('#58bcae', '#1c7d70'), ('#b89ce4', '#7551a6'), ('#e38bb1', '#a34670'), ('#c9b755', '#7f6e11'), ('#78bbdf', '#276e97'), ('#97b06e', '#57772d')]

@lru_cache(maxsize=1)
def _catalogue_colours():
    import json
    from pathlib import Path
    return json.loads(Path(__file__).with_name('reference-colours.json').read_text())

def reference_colour(molecule):
    accession = molecule.get('refseq_accession') or molecule.get('accession')
    if accession in _catalogue_colours():
        return _catalogue_colours()[accession]
    if molecule.get('molecule_type') == 'chromosome':
        return CHROMOSOME
    key = accession or molecule.get('replicon_name') or molecule.get('name') or 'unknown'
    rank = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16) % len(PLASMIDS)
    return PLASMIDS[rank]

def build_reference_origins(case, record, artifact, segment_identities=None, recorded_plot=None):
    molecules = [m for m in case.get('replicons', []) if record.get('tool') != 'plassembler' or m.get('molecule_type') == 'plasmid']
    references = []
    for molecule in molecules:
        colour, light = reference_colour(molecule)
        references.append({'id': molecule.get('refseq_accession'), 'name': molecule.get('replicon_name', 'Reference molecule'), 'length_bp': molecule.get('length_bp'), 'colour': colour, 'light_colour': light})
    graph = artifact.get('graph') or {}
    result = {'schema_version': 1, 'method': 'saved_exact_contig_gfa_association_v3', 'references': references, 'nodes': {}, 'contig_alignments': {}, 'node_intervals': {}, 'internal_boundaries_status': 'not_measured', 'scope': 'Whole-segment association through an exact contig and a recorded GFA path or verified whole-segment/contig sequence hash identity; not a within-node alignment map.', 'unassigned_reason': 'No saved exact-contig-to-GFA-path association is available for this segment.', 'source_hashes': {'assembly_sha256': record.get('assembly_sha256'), 'gfa_sha256': graph.get('source', {}).get('file_sha256')}}
    attached_hash = artifact.get('input_hashes', {}).get('assembly_sha256')
    if not record.get('assembly_sha256') or attached_hash != record['assembly_sha256'] or artifact.get('failed_execution_provenance') or (graph.get('source', {}).get('role') != 'final') or (graph.get('status') != 'available') or (graph.get('complete') is not True):
        result['unassigned_reason'] = 'A complete final graph bound to the scored assembly is required; no final-reference colours are assigned here.'
        return result
    from .node_intervals import build_node_intervals
    result['node_intervals'] = build_node_intervals(artifact.get('reference_interval_evidence'), graph.get('nodes', []), references, {**result['source_hashes'], 'truth_sha256': record.get('truth_sha256')})
    if result['node_intervals']:
        result['internal_boundaries_status'] = 'recorded_alignment_spans'
    node_ids = {n['id'] for n in graph.get('nodes', [])}
    paths, repeated_paths = ({}, set())
    for path in graph.get('paths', []):
        if path['id'] in paths:
            repeated_paths.add(path['id'])
        paths[path['id']] = path
    allowed_refs = {r['id'] for r in references}
    candidates = {}
    for index, molecule in enumerate((record.get('evaluation') or {}).get('replicons', [])):
        accession = molecule.get('accession')
        if accession not in allowed_refs:
            continue
        for contig in molecule.get('exact_contigs', []):
            path = paths.get(contig)
            if not path or contig in repeated_paths or (not path.get('steps')) or any((s.get('segment') not in node_ids or s.get('orientation') not in {'+', '-'} for s in path['steps'])):
                continue
            for step in path['steps']:
                evidence = {'reference_id': accession, 'contig_id': contig, 'path_id': path['id'], 'orientation': step['orientation'], 'exact_source': f'evaluation.replicons[{index}].exact_contigs', 'path_source': 'graph_artifacts.graph.paths', 'association_kind': 'exact_contig_path'}
                entries = candidates.setdefault(step['segment'], [])
                if evidence not in entries:
                    entries.append(evidence)
    if segment_identities:
        result['source_hashes']['graph_contig_identity_sha256'] = segment_identities['file_sha256']
        for index, molecule in enumerate((record.get('evaluation') or {}).get('replicons', [])):
            accession = molecule.get('accession')
            if accession not in allowed_refs:
                continue
            for association in segment_identities['associations']:
                if association['contig_id'] not in molecule.get('exact_contigs', []):
                    continue
                evidence = {'reference_id': accession, 'contig_id': association['contig_id'], 'orientation': association['orientation'], 'association_kind': 'whole_segment_sequence_identity', 'length_bp': association['length_bp'], 'sequence_sha256': association['sequence_sha256'], 'exact_source': f'evaluation.replicons[{index}].exact_contigs', 'identity_source': 'graph_contig_identity.json', 'identity_source_sha256': segment_identities['file_sha256']}
                candidates.setdefault(association['segment_id'], []).append(evidence)
    for node, evidence in candidates.items():
        ids = sorted({entry['reference_id'] for entry in evidence})
        kind = 'ambiguous' if len(ids) != 1 else 'verified_whole_segment' if any((e.get('association_kind') == 'whole_segment_sequence_identity' for e in evidence)) else 'path_inferred'
        result['nodes'][node] = {'status': 'supported' if len(ids) == 1 else 'ambiguous', 'reference_id': ids[0] if len(ids) == 1 else None, 'evidence_class': kind, 'candidate_reference_ids': ids, 'evidence': evidence}
    contigs = {e['contig_id'] for evidence in candidates.values() for e in evidence}
    result['contig_alignments'] = saved_contig_alignments(record, recorded_plot, contigs)
    return result

def saved_contig_alignments(record, plot, contigs):
    """Copy source-bound saved coordinates; do not project path nodes onto a reference."""
    if not plot or plot.get('status') != 'available':
        return {}
    hashes = plot.get('input_hashes') or {}
    if not all((record.get(k) and hashes.get(k) == record[k] for k in ('assembly_sha256', 'truth_sha256'))):
        return {}
    result = {}
    for index, row in enumerate(plot.get('alignments', [])):
        name = row.get('query_id')
        if name not in contigs:
            continue
        item = result.setdefault(name, {'coordinate_system': '0-based half-open', 'scope': 'output_contig_to_reference', 'source_kind': plot.get('source_kind', 'reviewed_coordinates'), 'total_rows': 0, 'rows': []})
        item['total_rows'] += 1
        if len(item['rows']) >= 20:
            continue
        item['rows'].append({k: row[k] for k in ('reference_id', 'query_id', 'reference_interval', 'query_interval', 'strand') if k in row} | {'source_row': index})
    return result
