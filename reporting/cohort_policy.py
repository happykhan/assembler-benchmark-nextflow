"""Classify saved case metadata for reporting; never select inputs or run analyses."""

def reporting_role(case, family, policy):
    if not policy or family not in policy.get('families', ['S1', 'S2', 'S3']):
        return ('primary', None)
    threshold = policy['minimum_plasmid_bp']
    molecules = case.get('replicons', [])
    chromosomes = [m for m in molecules if m.get('molecule_type') == 'chromosome']
    plasmids = [m for m in molecules if m.get('molecule_type') == 'plasmid']
    if family == 'S5':
        if case.get('assembly_accession') not in policy.get('linear_assemblies', []):
            return ('supplementary', 'Earlier isolated-plasmid control; replaced by the complete Streptomyces genome panel.')
        if len(chromosomes) != 1 or any((m.get('topology') != 'linear' for m in molecules)):
            return ('supplementary', 'The active S5 panel requires the selected complete linear reference complement.')
        return ('primary', None)
    if len(chromosomes) != 1:
        return ('supplementary', 'The revised baseline requires one chromosome.')
    if family in {'S2', 'S3', 'S6'} and (not plasmids):
        return ('supplementary', 'This family requires a larger-plasmid input.')
    if any((type(m.get('length_bp')) is not int or m['length_bp'] <= 0 for m in plasmids)):
        return ('supplementary', 'Plasmid length metadata is incomplete.')
    if any((m['length_bp'] < threshold for m in plasmids)):
        return ('supplementary', f'Input includes a plasmid smaller than {threshold:,} bp.')
    return ('primary', None)
