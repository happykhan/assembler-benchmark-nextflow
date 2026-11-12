"""Backend endpoint descriptions from immutable saved scores."""

def case_title(case):
    """Clarify short simulated Nanopore reads without changing frozen cases."""
    title = case.get('title', case['id'])
    if case.get('category') == 'S4' and case.get('read_length_profile') == 'short':
        mean = case.get('simulation', {}).get('length_mean')
        if isinstance(mean, (int, float)) and mean > 0:
            context = title.rsplit(' · ', 1)[0]
            return f'{context} · Short Nanopore read-length challenge · {mean / 1000:g} kb target mean'
    return title

def assessed_molecules(record):
    """Select the molecules relevant to the recorded endpoint, not a new policy."""
    if record.get('report_evidence'):
        required = set(record['report_evidence']['required_accessions'])
        return [m for m in (record.get('evaluation') or {}).get('replicons', []) if m.get('accession') in required]
    molecules = (record.get('evaluation') or {}).get('replicons', [])
    plasmids = [m for m in molecules if m.get('molecule_type') == 'plasmid']
    if plasmids or record.get('tool') == 'plassembler':
        return plasmids
    return molecules

def molecule_label(molecule):
    name = molecule.get('name', molecule.get('accession', 'Expected molecule'))
    length = molecule.get('length_bp')
    return f'{name} ({length:,} bp)' if isinstance(length, int) and (not isinstance(length, bool)) and (length > 0) else name

def verdict(record):
    if record.get('status') == 'timeout' or record.get('execution_outcome') == 'did_not_complete':
        return ('Fail — did not complete', record.get('error') or 'The run exceeded its time limit.')
    if record.get('report_evidence'):
        return (record['report_evidence']['heading'], record['report_evidence']['description'])
    status = record['status']
    if status not in {'pass', 'fail'}:
        return ('No completed exact assessment', record.get('error') or 'This run has no completed sequence verdict.')
    if not record.get('evaluation'):
        return (f'{status.title()} — recorded exact endpoint', 'Per-molecule assessment details are not recorded for this run.')
    molecules = assessed_molecules(record)
    failed = [m for m in molecules if m.get('status') != 'pass']
    if status == 'pass':
        if not molecules and record.get('tool') == 'plassembler':
            return ('Pass — chromosome-only negative control', 'The saved output meets the no-plasmid endpoint.')
        return ('Pass — exact recovery', 'Every molecule required by this endpoint has a complete, separate exact match.')
    names = ', '.join((molecule_label(m) for m in failed))
    heading = f'Fail — {names} not recovered exactly' if names else 'Fail — the exact endpoint was not met'
    review = record.get('sequence_review') or {}
    from .failure_summary import review_matches_execution
    if review_matches_execution(record) and review.get('summary'):
        return (heading, review['summary'])
    if failed:
        if all((not m.get('exact_contigs') for m in failed)):
            return (heading, 'No complete, separate copy matches the reference sequence.')
        return (heading, 'Exact matches were recorded, but their copy count or assignment does not meet the saved criterion.')
    return (heading, 'Inspect the saved exact criterion and assessment below for the recorded reason.')
