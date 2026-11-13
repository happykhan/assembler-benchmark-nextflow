"""Johnson 2023 summed-block recovery rule, separate from longest alignment."""
from collections import defaultdict

METHOD = 'johnson-2023-summed-block-rule-v1'


def summarise_paper(path, references, assembly, molecule_types):
    """PAF orientation: native reference query -> draft assembly target (asm5)."""
    groups = defaultdict(lambda: defaultdict(int))
    seen = set()
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        f = line.split('\t')
        if len(f) < 12 or f[0] not in references or int(f[1]) != len(references[f[0]]):
            raise ValueError('Paper PAF query inventory differs')
        seen.add(f[0])
        if f[5] == '*':
            if int(f[6]) != 0 or int(f[10]) != 0:
                raise ValueError('Malformed no-hit PAF record')
            continue
        if (f[5] not in assembly or int(f[6]) != len(assembly[f[5]])
                or not 0 <= int(f[2]) < int(f[3]) <= int(f[1])
                or not 0 <= int(f[7]) < int(f[8]) <= int(f[6])
                or not 0 <= int(f[9]) <= int(f[10]) or int(f[10]) <= 0):
            raise ValueError('Paper PAF target inventory or geometry differs')
        groups[f[0]][f[5]] += int(f[10])
    if seen != set(references):
        raise ValueError('Paper PAF lacks an explicit alignment or no-hit row for every reference')
    output = []
    for accession, sequence in references.items():
        if molecule_types.get(accession) != 'plasmid':
            continue
        hits = groups[accession]
        # Integer comparisons preserve the paper's strict >90%, including ties.
        passing = [q for q, blocks in hits.items() if 10 * blocks > 9 * len(sequence)]
        total = sum(hits.values())
        fragmented = not passing and 10 * total > 9 * len(sequence)
        retained = passing if passing else list(hits)
        output.append({'accession': accession, 'method': METHOD, 'status': 'measured',
                       'recovered': bool(passing or fragmented), 'fragmented_recovery': fragmented,
                       'duplicate_recovering_contigs': len(passing) > 1,
                       'chromosome_incorporation_heuristic': bool(passing or fragmented) and any(len(assembly[q]) > 1000000 for q in retained),
                       'summed_alignment_blocks_bp': total, 'summed_block_fraction': total / len(sequence),
                       'recovering_contig_count': len(passing),
                       'per_draft_contig_block_bp': dict(hits),
                       'note': 'Strict >90% summed PAF blocks; overlapping/secondary contributions are not deduplicated. Not a sequence-breadth or structural-correctness test.'})
    return output
