"""Alignment evidence explaining exact-recovery failures, without changing scores."""

from collections import Counter, defaultdict
from pathlib import Path
import re


DEFAULT_POLICY = {
    "minimum_mapq": 20,
    "minimum_identity": 0.90,
    "minimum_aligned_bp": 200,
    "duplication_fraction": 0.20,
    "fragmentation_gain_fraction": 0.05,
    "complete_fraction": 0.95,
    "maximum_query_overlap_fraction": 0.20,
}


def minimap2_command(truth_fasta, assembly_fasta, threads=1):
    """Return argv only; caller captures version, stderr, exit code and PAF."""
    if not isinstance(threads, int) or isinstance(threads, bool) or threads < 1:
        raise ValueError("Alignment threads must be a positive integer")
    return ["minimap2", "-x", "asm5", "-c", "--secondary=yes", "--seed", "11",
            "-t", str(threads), str(truth_fasta), str(assembly_fasta)]


def merge_intervals(intervals):
    merged = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def interval_bp(intervals):
    return sum(end - start for start, end in merge_intervals(intervals))


def intersection(left, right):
    a, b = merge_intervals(left), merge_intervals(right)
    result = []
    i = j = 0
    while i < len(a) and j < len(b):
        start, end = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if start < end:
            result.append((start, end))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return result


def query_overlap(left, right):
    overlap = max(0, min(left["query_end"], right["query_end"]) - max(left["query_start"], right["query_start"]))
    return overlap / min(left["query_end"] - left["query_start"], right["query_end"] - right["query_start"])


def read_paf(path):
    """Read mapped PAF records; malformed coordinates/CIGAR raise ValueError."""
    rows = []
    for number, line in enumerate(Path(path).read_text().splitlines(), 1):
        if not line.strip():
            continue
        fields = line.split("\t")
        try:
            if len(fields) < 12:
                raise ValueError("fewer than 12 PAF fields")
            query, qlen, qs, qe, strand, target, tlen, ts, te, matches, block, mapq = fields[:12]
            qlen, qs, qe, tlen, ts, te, matches, block, mapq = map(int, (qlen, qs, qe, tlen, ts, te, matches, block, mapq))
            if not query or not target or strand not in ("+", "-") or not (0 <= qs < qe <= qlen and 0 <= ts < te <= tlen):
                raise ValueError("invalid PAF coordinates or strand")
            if not (0 <= matches <= block and block > 0 and 0 <= mapq <= 255):
                raise ValueError("invalid PAF match, block or mapQ values")
            tags = {}
            for field in fields[12:]:
                key, kind, value = field.split(":", 2)
                if key in tags:
                    raise ValueError("duplicate PAF tag")
                tags[key] = (kind, value)
            ambiguous = int(tags.get("nn", ("i", "0"))[1])
            if ambiguous < 0:
                raise ValueError("Invalid ambiguous-base count")
            cigar = tags.get("cg", (None, None))
            blocks = []
            if cigar[0] == "Z":
                operations = re.findall(r"([1-9][0-9]*)([MID=X])", cigar[1])
                if not operations or "".join(n + op for n, op in operations) != cigar[1]:
                    raise ValueError("unsupported or invalid assembly CIGAR")
                target_pos, query_bp, alignment_bp = ts, 0, 0
                for size, operation in operations:
                    size = int(size)
                    alignment_bp += size
                    if operation in "M=X":
                        blocks.append((target_pos, target_pos + size))
                    if operation in "MD=X":
                        target_pos += size
                    if operation in "MI=X":
                        query_bp += size
                if target_pos != te or query_bp != qe - qs or alignment_bp != block + ambiguous:
                    raise ValueError("CIGAR disagrees with PAF spans/block length")
            rows.append({"query": query, "query_length": qlen, "query_start": qs, "query_end": qe,
                         "strand": strand, "target": target, "target_length": tlen,
                         "target_start": ts, "target_end": te, "matches": matches,
                         "block_length": block, "mapq": mapq, "type": tags.get("tp", (None, None))[1],
                         "base_alignment": bool(blocks), "ambiguous_bases": ambiguous, "target_blocks": blocks})
        except (ValueError, TypeError) as error:
            raise ValueError(f"PAF line {number}: {error}") from error
    return rows


def summarise_paf(case, paf_path, assembly_lengths=None, policy=None):
    """Summarise assembly-query/truth-target PAF, retaining exclusions and limits."""
    settings = {**DEFAULT_POLICY, **(policy or {})}
    if set(settings) != set(DEFAULT_POLICY):
        raise ValueError("Unknown alignment diagnostic policy key")
    if not (0 <= settings["minimum_mapq"] <= 254 and settings["minimum_aligned_bp"] > 0):
        raise ValueError("Invalid diagnostic mapQ or aligned-length threshold")
    for key in set(settings) - {"minimum_mapq", "minimum_aligned_bp"}:
        if not 0 <= settings[key] <= 1:
            raise ValueError(f"Invalid diagnostic fraction {key}")
    truth = {r["refseq_accession"]: r for r in case["replicons"]}
    if len(truth) != len(case["replicons"]) or any(r["length_bp"] <= 0 for r in truth.values()):
        raise ValueError("Replicon names must be unique and lengths positive")
    accepted, excluded, observed, seen = [], Counter(), set(), set()
    query_lengths = {}
    for row in read_paf(paf_path):
        accession = row["target"]
        if accession not in truth or row["target_length"] != truth[accession]["length_bp"]:
            raise ValueError("PAF target does not match this case's reference inventory")
        name = row["query"]
        if name in query_lengths and query_lengths[name] != row["query_length"]:
            raise ValueError("Inconsistent query length in PAF")
        query_lengths[name] = row["query_length"]
        if assembly_lengths is not None and assembly_lengths.get(name) != row["query_length"]:
            raise ValueError("PAF query does not match the assembly inventory")
        observed.add(name)
        identity = row["matches"] / row["block_length"]
        signature = tuple((k, tuple(v) if isinstance(v, list) else v) for k, v in row.items())
        reason = ("duplicate_paf_record" if signature in seen else
                  "secondary_or_unclassified" if row["type"] not in ("P", "I") else
                  "missing_base_alignment" if not row["base_alignment"] else
                  "ambiguous_bases" if row["ambiguous_bases"] else
                  "missing_mapq" if row["mapq"] == 255 else
                  "low_mapq" if row["mapq"] < settings["minimum_mapq"] else
                  "short_alignment" if interval_bp(row["target_blocks"]) < settings["minimum_aligned_bp"] else
                  "low_identity" if identity < settings["minimum_identity"] else None)
        seen.add(signature)
        if reason:
            excluded[reason] += 1
        else:
            accepted.append(row)
    by_query = defaultdict(list)
    by_target = defaultdict(list)
    for row in accepted:
        by_query[row["query"]].append(row)
        by_target[row["target"]].append(row)
    joins = []
    for query, rows in sorted(by_query.items()):
        pairs = set()
        for i, left in enumerate(rows):
            for right in rows[i + 1:]:
                if left["target"] != right["target"] and query_overlap(left, right) <= settings["maximum_query_overlap_fraction"]:
                    pairs.add(tuple(sorted((left["target"], right["target"]))))
        if pairs:
            joins.append({"contig": query, "replicon_pairs": [list(pair) for pair in sorted(pairs)]})
    replicons = []
    for accession, replicon in truth.items():
        rows = by_target[accession]
        length = replicon["length_bp"]
        covered = merge_intervals([block for row in rows for block in row["target_blocks"]])
        contigs = sorted({row["query"] for row in rows})
        per_contig = {query: interval_bp([block for row in rows if row["query"] == query for block in row["target_blocks"]]) / length for query in contigs}
        best = max(per_contig.values(), default=0)
        copy_overlap = []
        for i, left in enumerate(rows):
            for right in rows[i + 1:]:
                if left["query"] != right["query"] or query_overlap(left, right) <= settings["maximum_query_overlap_fraction"]:
                    copy_overlap.extend(intersection(left["target_blocks"], right["target_blocks"]))
        duplicated = interval_bp(copy_overlap) / length
        recovered = interval_bp(covered) / length
        denominator = sum(row["block_length"] for row in rows)
        joined = [item["contig"] for item in joins if any(accession in pair for pair in item["replicon_pairs"])]
        replicons.append({"accession": accession, "name": replicon["replicon_name"],
                          "molecule_type": replicon["molecule_type"], "length_bp": length,
                          "aligned_reference_bp": interval_bp(covered), "recovered_fraction": recovered,
                          "alignment_identity": sum(row["matches"] for row in rows) / denominator if denominator else None,
                          "identity_alignment_bp": denominator, "accepted_alignment_count": len(rows),
                          "contig_count": len(contigs), "contigs": contigs,
                          "best_contig_recovered_fraction": best, "per_contig_recovered_fraction": per_contig,
                          "duplicated_reference_fraction": duplicated,
                          "candidate_flags": {"no_supported_alignment": not rows,
                              "fragmented": len(contigs) > 1 and best < settings["complete_fraction"] and recovered - best >= settings["fragmentation_gain_fraction"],
                              "duplicated": duplicated >= settings["duplication_fraction"] and duplicated > 0,
                              "joined": bool(joined)}, "candidate_join_contigs": joined,
                          "topology_status": "not_assessed"})
    supported = set(by_query)
    inventory = set(assembly_lengths) if assembly_lengths is not None else observed
    return {"schema_version": 1, "metric_version": "paf-recovery-evidence-v1", "policy": settings,
            "replicons": replicons, "candidate_joins": joins, "accepted_alignment_count": len(accepted),
            "excluded_alignment_counts": dict(excluded), "assembly_inventory_complete": assembly_lengths is not None,
            "contigs_without_supported_alignment": sorted(inventory - supported),
            "identity_method": "sum PAF matching bases / sum alignment block lengths of retained base alignments; overlapping alignments contribute repeatedly",
            "limitations": "Alignment evidence only; strict scores unchanged. Conservative mapping filters may hide shared/repetitive or short sequence. Candidate flags are not confirmed structural errors. No circularity or topology claims. Circular-origin splits may be missed by alignment heuristics."}
