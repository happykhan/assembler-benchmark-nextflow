"""Longest-single-alignment metrics; failure metadata never proves absence."""
import hashlib
import json
import re
from pathlib import Path

METHOD = 'wick-longest-alignment-v1'


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read_fasta(path):
    sequences = {}
    name = None
    for line in Path(path).read_text().splitlines():
        if not line:
            continue
        if line.startswith('>'):
            name = line[1:].split()[0]
            if name in sequences:
                raise ValueError('Duplicate FASTA identifier: ' + name)
            sequences[name] = ''
        elif name is None:
            raise ValueError('FASTA sequence precedes identifier')
        else:
            sequences[name] += line.strip().upper()
    if any(not seq for seq in sequences.values()):
        raise ValueError('Empty FASTA record')
    return sequences


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def parse_paf(path, references, queries):
    rows = []
    for number, line in enumerate(Path(path).read_text().splitlines(), 1):
        if not line.strip():
            continue
        f = line.split('\t')
        if len(f) < 12:
            raise ValueError(f'Invalid PAF row {number}')
        qlen, qs, qe, rlen, rs, re_, matches, block, mapq = map(int, (f[1], f[2], f[3], f[6], f[7], f[8], f[9], f[10], f[11]))
        cigar = next((v[5:] for v in f[12:] if v.startswith('cg:Z:')), None)
        if (f[0] not in queries or f[5] not in references
                or len(queries[f[0]]) != qlen or 3 * len(references[f[5]]) != rlen
                or not 0 <= qs < qe <= qlen or not 0 <= rs < re_ <= rlen
                or f[4] not in ('+', '-') or not 0 <= matches <= block or block <= 0
                or not 0 <= mapq <= 255 or not cigar
                or not re.fullmatch(r'(?:[1-9][0-9]*[MIDNSHP=X])+', cigar)):
            raise ValueError(f'PAF row {number} disagrees with source inventories')
        operations = [(int(n), op) for n, op in re.findall(r'(\d+)([MIDNSHP=X])', cigar)]
        if (sum(n for n, op in operations if op in 'MDN=X') != re_ - rs
                or sum(n for n, op in operations if op in 'MI=X') != qe - qs):
            raise ValueError(f'PAF CIGAR span disagrees at row {number}')
        rows.append({'query': f[0], 'reference': f[5], 'query_start': qs, 'query_end': qe,
                     'reference_start': rs, 'reference_end': re_, 'strand': f[4],
                     'span': re_ - rs, 'identity': matches / block,
                     'max_indel_bp': max([n for n, op in operations if op in 'ID'] or [0])})
    return rows


def summarise(references, alignments, molecule_types=None):
    results = []
    molecule_types = molecule_types or {}
    for accession, sequence in references.items():
        matches = [row for row in alignments if row['reference'] == accession]
        best = max(matches, key=lambda a: (a['span'], -a['reference_start'])) if matches else None
        span = best['span'] if best else 0
        measured = bool(best and (span > 100000 or span > len(sequence) / 4))
        results.append({'accession': accession, 'length_bp': len(sequence),
                        'molecule_type': molecule_types.get(accession, 'unknown'),
                        'contiguity': span / len(sequence), 'complete': span / len(sequence) >= .99,
                        'longest_alignment_span_bp': span, 'alignment_count': len(matches),
                        'contig_id': best['query'] if best else None,
                        'identity_measured': measured,
                        'identity': best['identity'] if measured else None,
                        'max_indel_bp': best['max_indel_bp'] if measured else None,
                        'reference_interval_tripled_0based_half_open': [best['reference_start'], best['reference_end']] if best else None,
                        'query_interval_0based_half_open': [best['query_start'], best['query_end']] if best else None,
                        'strand': best['strand'] if best else None})
    return results


def standard_reference_binding(case, simulation, provenance, provenance_sha256):
    """Native beta inputs bind canonical FASTA; legacy inputs also bind JSON."""
    receipt = simulation.get('reference_provenance_sha256')
    if receipt == provenance_sha256:
        return 'reference_metadata_sha256'
    if (receipt is None and case.get('simulation_method') == 'native-error-free-v1'
            and simulation.get('version') == 'native-error-free-v1'
            and simulation.get('reference_mode') == 'whole_genome'
            and simulation.get('reference_sha256') == provenance.get('reference_sha256')
            and provenance.get('reference_sha256')
            and {r['accession'] for r in simulation.get('replicons', [])}
                == {r['accession'] for r in provenance.get('molecules', [])}):
        return 'canonical_reference_fasta_sha256'
    raise ValueError('Standard simulation/preparation provenance binding differs')


def outcome(replicons, query_count):
    if not query_count:
        return 'empty'
    if all(row['complete'] for row in replicons):
        return 'fully_complete'
    chromosomes = [row for row in replicons if row['molecule_type'] == 'chromosome']
    if chromosomes and all(row['complete'] for row in chromosomes):
        return 'chromosome_complete'
    return 'incomplete'
