"""Strict exact-sequence endpoint for the error-free pilot only."""

from .common import fasta, reverse_complement


def equivalent(reference, query, topology):
    if len(reference) != len(query):
        return False
    if topology == "circular":
        doubled = reference + reference
        return query in doubled or reverse_complement(query) in doubled
    return query == reference or reverse_complement(query) == reference


def evaluate(case, truth_path, assembly_path, plasmid_only=False):
    truth = fasta(truth_path)
    contigs = fasta(assembly_path)
    rows = []
    for replicon in case["replicons"]:
        sequence = truth[replicon["refseq_accession"]]
        matches = [name for name, query in contigs.items() if equivalent(sequence, query, replicon["topology"])]
        # A second full copy inside another molecule also invalidates unique recovery.
        embedded = []
        if replicon["molecule_type"] == "plasmid":
            for name, query in contigs.items():
                if name in matches or len(query) <= len(sequence):
                    continue
                if sequence in query or reverse_complement(sequence) in query:
                    embedded.append(name)
        passed = len(matches) == 1 and not embedded
        rows.append({"accession": replicon["refseq_accession"], "name": replicon["replicon_name"],
                     "molecule_type": replicon["molecule_type"], "length_bp": len(sequence),
                     "status": "pass" if passed else "fail", "exact_contigs": matches,
                     "extra_full_copy_contigs": embedded, "topology_status": "not_assessed",
                     "recovered_fraction": 1.0 if matches else None,
                     "reason": "One exact dedicated molecule" if passed else "Duplicate/embedded full copy" if len(matches) > 1 or embedded else "No exact dedicated molecule; partial recovery and error cause are not yet classified"})
    plasmids = [r for r in rows if r["molecule_type"] == "plasmid"]
    if plasmids:
        passed = all(r["status"] == "pass" for r in plasmids)
        endpoint = "All expected plasmids recovered exactly once as dedicated molecules"
    elif plasmid_only:
        passed = not contigs
        endpoint = "No plasmid sequence reported in the chromosome-only control"
    else:
        passed = len(contigs) == 1 and all(r["status"] == "pass" for r in rows)
        endpoint = "Chromosome-only assembly contains exactly the expected chromosome"
    matched = {name for r in rows for name in r["exact_contigs"]}
    return {"status": "pass" if passed else "fail", "endpoint": endpoint, "replicons": rows,
            "plasmid_passes": sum(r["status"] == "pass" for r in plasmids), "plasmid_total": len(plasmids),
            "contig_count": len(contigs), "unclassified_contigs": [n for n in contigs if n not in matched],
            "limitations": "Sequence endpoint only. Circularity claims and partial/structural alignment metrics are not assessed. Extra contigs are retained, not automatically called plasmids."}
