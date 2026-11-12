"""Per-molecule read support; never an assembler recovery verdict."""


def summarise_read_paf(paf, references):
    intervals = {name: [] for name in references}
    read_ids = {name: set() for name in references}
    aligned = {name: 0 for name in references}
    with paf.open() as stream:
        for line in stream:
            f = line.rstrip().split('\t')
            if len(f) < 12 or f[5] not in references or int(f[6]) != len(references[f[5]]):
                raise ValueError('Read diagnostic PAF inventory differs')
            start, end = int(f[7]), int(f[8])
            if not 0 <= start < end <= int(f[6]):
                raise ValueError('Read diagnostic alignment range differs')
            intervals[f[5]].append((start, end))
            read_ids[f[5]].add(f[0])
            aligned[f[5]] += end - start
    rows = []
    for name, sequence in references.items():
        covered = 0
        finish = 0
        for start,end in sorted(intervals[name]):
            covered += max(0, end - max(start, finish))
            finish = max(finish, end)
        rows.append({'accession': name, 'length_bp': len(sequence), 'distinct_mapped_read_ids': len(read_ids[name]),
                     'covered_reference_bases': covered, 'reference_breadth': covered/len(sequence),
                     'aligned_target_bases': aligned[name], 'mean_aligned_target_depth': aligned[name]/len(sequence)})
    return rows
