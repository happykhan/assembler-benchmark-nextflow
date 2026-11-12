"""Pinned Badread errors on frozen exact fragments; no fragment resampling."""

from collections import Counter
from contextlib import contextmanager
import csv
import gzip
import hashlib
import importlib
import importlib.metadata
import io
from itertools import zip_longest
import math
from pathlib import Path
import platform
import random
import re
import shutil
import statistics

from .common import ROOT, digest, fasta, fingerprint, load, reverse_complement, save


ADAPTER_VERSION = "badread-matched-fragments-v1"
PAIRS = {("random", "ideal"), ("nanopore2023", "nanopore2023")}
ORIGIN_FIELDS = ["read_id", "replicon", "start_0based", "length", "strand"]
GEOMETRY_FIELDS = ["seed", "chromosome_depth", "plasmid_relative_depth", "length_mean", "length_sd",
                   "length_min", "length_max", "circular_read_limit", "minimum_breadth"]


def _models(profile):
    pair = (profile.get("error_model"), profile.get("qscore_model"))
    if pair not in PAIRS:
        raise ValueError("Only random/ideal and nanopore2023/nanopore2023 are supported")
    return pair


def inspect_runtime(profile):
    """Hash the installed simulator before preparation freezes its expected hash."""
    error_model, qscore_model = _models(profile)
    module = importlib.import_module("badread.simulate")
    version = importlib.import_module("badread.version").__version__
    if version != "0.4.2":
        raise ValueError("The matched-fragment adapter requires Badread 0.4.2")
    root = Path(module.__file__).resolve().parent
    sources = {path.name: digest(path) for path in sorted(root.glob("*.py"))}
    required = {"simulate.py", "error_model.py", "qscore_model.py", "misc.py", "settings.py", "version.py"}
    if not required.issubset(sources):
        raise ValueError("Installed Badread source files are incomplete")
    assets = {}
    for folder, model in (("error_models", error_model), ("qscore_models", qscore_model)):
        if model not in ("random", "ideal"):
            path = root / folder / (model + ".gz")
            if not path.is_file():
                raise ValueError("Installed Badread model asset is missing: " + str(path))
            assets[folder + "/" + path.name] = digest(path)
    numpy = importlib.import_module("numpy")
    edlib = importlib.import_module("edlib")
    runtime = {"badread_version": version, "python": platform.python_version(),
               "numpy_version": numpy.__version__, "edlib_version": importlib.metadata.version("edlib"),
               "badread_sources_sha256": sources, "model_assets_sha256": assets,
               "numpy_rng_binary_sha256": digest(Path(importlib.import_module("numpy.random.mtrand").__file__)),
               "model_pair": [error_model, qscore_model], "adapter_version": ADAPTER_VERSION,
               "adapter_sha256": digest(Path(__file__)), "edlib_binary_sha256": digest(Path(edlib.__file__))}
    return {"runtime": runtime, "sha256": fingerprint(runtime)}


class BadreadBackend:
    def __init__(self, profile):
        self.numpy = importlib.import_module("numpy")
        self.edlib = importlib.import_module("edlib")
        self.simulate = importlib.import_module("badread.simulate")
        errors = importlib.import_module("badread.error_model")
        qualities = importlib.import_module("badread.qscore_model")
        with self.seeded("0" * 64):
            self.error_model = errors.ErrorModel(profile["error_model"], output=io.StringIO())
            self.qscore_model = qualities.QScoreModel(profile["qscore_model"], output=io.StringIO())
        # Badread lazily adds residual probability alternatives. Normalise once so
        # the model's mutable initialisation cannot depend on read traversal order.
        if self.error_model.type == "model":
            for key, probabilities in self.error_model.probabilities.items():
                residual = 1.0 - sum(probabilities)
                if residual > 0:
                    self.error_model.alternatives[key].append(None)
                    probabilities.append(residual)

    @contextmanager
    def seeded(self, seed_hex):
        python_state, numpy_state = random.getstate(), self.numpy.random.get_state()
        random.seed(int(seed_hex, 16))
        self.numpy.random.seed([int(seed_hex[i:i + 8], 16) for i in range(0, 64, 8)])
        try:
            yield
        finally:
            random.setstate(python_state)
            self.numpy.random.set_state(numpy_state)

    def generate(self, fragment, target_identity, seed_hex):
        with self.seeded(seed_hex):
            return self.simulate.sequence_fragment(fragment, target_identity, self.error_model, self.qscore_model)

    def align(self, emitted, fragment):
        return self.edlib.align(emitted, fragment, mode="NW", task="path")


def _profile(profile):
    _models(profile)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", profile.get("id", "")):
        raise ValueError("Noise profile needs a simple identifier")
    if not re.fullmatch(r"[0-9a-f]{64}", profile.get("expected_runtime_sha256", "")):
        raise ValueError("Freeze expected_runtime_sha256 during preparation before transforming reads")
    if any(profile.get("additional_problems", {}).values()):
        raise ValueError("This adapter does not add adapters, chimeras, junk, glitches or plasmid loss")
    params = profile.get("identity_beta_percent", {})
    if set(params) != {"mean", "maximum", "sd"}:
        raise ValueError("Specify identity beta mean, maximum and sd explicitly")
    mean, maximum, sd = (params[key] for key in ("mean", "maximum", "sd"))
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in (mean, maximum, sd)):
        raise ValueError("Identity parameters must be finite numbers")
    if not (50 <= mean <= maximum <= 100 and sd >= 0):
        raise ValueError("Invalid identity distribution")
    if sd == 0:
        return mean / 100, None, None
    if mean == maximum:
        raise ValueError("A varying beta identity distribution requires mean below maximum")
    unit_mean, variance = mean / maximum, (sd / maximum) ** 2
    concentration = unit_mean * (1 - unit_mean) / variance - 1
    alpha, beta = unit_mean * concentration, (1 - unit_mean) * concentration
    if alpha <= 0 or beta <= 0:
        raise ValueError("Identity parameters do not define a beta distribution")
    return maximum / 100, alpha, beta


def _inside(path):
    path = Path(path).resolve()
    return path


@contextmanager
def _gzip_output(path):
    with Path(path).open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=6) as zipped:
            with io.TextIOWrapper(zipped, encoding="ascii", newline="\n") as stream:
                yield stream


def _fastq(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="ascii") as stream:
        while True:
            header = stream.readline()
            if not header:
                return
            sequence, plus, quality = (stream.readline().rstrip("\r\n") for _ in range(3))
            name = header.rstrip("\r\n")[1:]
            if not header.startswith("@") or not name or any(char.isspace() for char in name) or plus != "+":
                raise ValueError("Expected clean four-line FASTQ with simple preserved read IDs")
            if not sequence or set(sequence) - set("ACGT") or len(sequence) != len(quality):
                raise ValueError("Invalid clean FASTQ sequence or quality length")
            yield name, sequence


def alignment_evidence(emitted, fragment, quality, alignment):
    """Indel-aware global identity and quality calibration from final output only."""
    cigar = alignment.get("cigar")
    parts = re.findall(r"([1-9][0-9]*)([=XID])", cigar or "")
    if not parts or "".join(size + operation for size, operation in parts) != cigar:
        raise ValueError("Edlib returned an invalid extended global CIGAR")
    counts = Counter({"=": 0, "X": 0, "I": 0, "D": 0})
    q = t = 0
    quality_errors = Counter()
    fragment_intervals = []
    for size, operation in parts:
        size = int(size)
        counts[operation] += size
        if operation in "=X":
            left, right = emitted[q:q + size], fragment[t:t + size]
            if len(left) != size or len(right) != size or any((a == b) != (operation == "=") for a, b in zip(left, right)):
                raise ValueError("Global CIGAR disagrees with final read/fragment bases")
        if operation in "=X":
            fragment_intervals.append((t, t + size))
        if operation in "XI":
            quality_errors.update(ord(value) - 33 for value in quality[q:q + size])
        if operation in "=XI":
            q += size
        if operation in "=XD":
            t += size
    if q != len(emitted) or t != len(fragment) or alignment.get("editDistance") != counts["X"] + counts["I"] + counts["D"]:
        raise ValueError("Global CIGAR does not consume both sequences or match edit distance")
    denominator = sum(counts.values())
    return {"identity": counts["="] / denominator, "matches": counts["="], "substitutions": counts["X"],
            "insertions": counts["I"], "deletions": counts["D"], "alignment_columns": denominator,
            "cigar": cigar, "quality_errors": quality_errors, "fragment_aligned_intervals": fragment_intervals}


def project_fragment_intervals(intervals, start, source_length, strand, reference_length):
    """Project oriented fragment alignment blocks through known circular origins."""
    result = []
    for left, right in intervals:
        if strand == "-":
            left, right = source_length - right, source_length - left
        left, right = start + left, start + right
        if left >= reference_length:
            left, right = left - reference_length, right - reference_length
        result.append((left, min(right, reference_length)))
        if right > reference_length:
            result.append((0, right - reference_length))
    return result


def _length_stats(values):
    if not values:
        return {"count": 0, "minimum": None, "maximum": None, "mean": None, "sd": None, "n50": None, "quantiles": {}}
    ordered = sorted(values)
    half, total = sum(values) / 2, 0
    n50 = None
    for length in reversed(ordered):
        total += length
        if total >= half:
            n50 = length
            break
    return {"count": len(values), "minimum": ordered[0], "maximum": ordered[-1],
            "mean": statistics.mean(values), "sd": statistics.pstdev(values), "n50": n50,
            "quantiles": {str(percent): ordered[round((len(ordered) - 1) * percent / 100)] for percent in (5, 25, 50, 75, 95)}}


def _union_bp(intervals):
    end = total = 0
    for start, stop in sorted(intervals):
        if stop > end:
            total += stop - max(start, end)
            end = stop
    return total


def _replicon_summary(replicon, stats, settings, mean_identity, sd_identity):
    length = replicon["length_bp"]
    source_bases, emitted_bases = sum(stats["source_lengths"]), sum(stats["emitted_lengths"])
    target = length * settings["chromosome_depth"] * (settings["plasmid_relative_depth"] if replicon["molecule_type"] == "plasmid" else 1)
    breadth = _union_bp(stats["intervals"]) / length
    effective_count = source_bases ** 2 / sum(value ** 2 for value in stats["source_lengths"]) if source_bases else 0
    weighted_identity = sum(identity * size for identity, size in zip(stats["identities"], stats["source_lengths"])) / source_bases if source_bases else None
    tolerance_pp = max(0.5, 4 * sd_identity / math.sqrt(effective_count)) if effective_count else None
    holds = []
    if not stats["source_lengths"] or source_bases < target or source_bases - stats["source_lengths"][-1] >= target:
        holds.append("Source depth/one-fragment stopping policy was not satisfied")
    if breadth < settings["minimum_breadth"]:
        holds.append("Source breadth is below the frozen minimum")
    if weighted_identity is None or abs(weighted_identity * 100 - mean_identity) > tolerance_pp:
        holds.append("Final achieved mean identity is outside the predeclared validation band")
    qualities = stats["qualities"]
    quality_count = sum(qualities.values())
    quality_mean = sum(q * count for q, count in qualities.items()) / quality_count if quality_count else None
    calibration = [{"phred": q, "emitted_bases": qualities[q], "substitutions_or_insertions": stats["quality_errors"][q],
                    "observed_error_fraction": stats["quality_errors"][q] / qualities[q],
                    "nominal_error_probability": 10 ** (-q / 10)} for q in sorted(qualities)]
    return {"accession": replicon["refseq_accession"], "target_depth": target / length,
            "achieved_depth": emitted_bases / length, "breadth": breadth, "breadth_basis": "source_fragment_union",
            "source_depth": source_bases / length, "emitted_depth": emitted_bases / length,
            "source_breadth": breadth, "emitted_breadth": sum(stats["emitted_coverage"]) / length,
            "emitted_breadth_basis": "final-read global alignment blocks projected through known source origins; deletions excluded",
            "emitted_aligned_reference_depth": (source_bases - stats["errors"]["deletions"]) / length,
            "source_bases": source_bases, "sequenced_bases": emitted_bases, "read_count": len(stats["source_lengths"]),
            "mean_read_length": emitted_bases / len(stats["emitted_lengths"]) if stats["emitted_lengths"] else None,
            "minimum_read_length": min(stats["emitted_lengths"], default=None), "maximum_read_length": max(stats["emitted_lengths"], default=None),
            "source_length_stats": _length_stats(stats["source_lengths"]), "emitted_length_stats": _length_stats(stats["emitted_lengths"]),
            "identity_stats": {"mean_per_read": statistics.mean(stats["identities"]) if stats["identities"] else None,
                               "sd_per_read": statistics.pstdev(stats["identities"]) if stats["identities"] else None,
                               "quantiles": {str(p): sorted(stats["identities"])[round((len(stats["identities"]) - 1) * p / 100)] for p in (5, 25, 50, 75, 95)} if stats["identities"] else {},
                               "source_base_weighted_mean": weighted_identity, "effective_read_count": effective_count,
                               "validation_tolerance_percentage_points": tolerance_pp,
                               "minimum": min(stats["identities"], default=None), "maximum": max(stats["identities"], default=None)},
            "error_counts": dict(stats["errors"]),
            "quality_stats": {"minimum": min(qualities, default=None), "maximum": max(qualities, default=None), "mean": quality_mean,
                              "sd": math.sqrt(sum((q - quality_mean) ** 2 * count for q, count in qualities.items()) / quality_count) if quality_count else None,
                              "histogram": {str(q): count for q, count in sorted(qualities.items())}, "calibration": calibration,
                              "calibration_basis": "emitted bases; substitutions and insertions have qualities, deletions do not"},
            "validation_holds": holds}


def transform_fragments(clean_fastq_gz, clean_origins_tsv_gz_orplain, output_dir, profile, case):
    """Write noisy FASTQ/origins/audit and noisy-input.json; statistical holds invalidate input.

    The clean FASTQ's directory must also contain its frozen input.json and
    truth.fasta. Structural/provenance corruption raises before a valid manifest
    can be written. The caller owns publishing the returned record as input.json.
    """
    maximum, alpha, beta = _profile(profile)
    runtime = inspect_runtime(profile)
    if runtime["sha256"] != profile["expected_runtime_sha256"]:
        raise ValueError("Badread source/model/runtime hash differs from frozen preparation")
    clean_reads, origins_path, output = map(_inside, (clean_fastq_gz, clean_origins_tsv_gz_orplain, output_dir))
    clean_manifest_path = _inside(clean_reads.parent / "input.json")
    truth_path = _inside(clean_reads.parent / "truth.fasta")
    clean_manifest = load(clean_manifest_path)
    if clean_manifest.get("status") != "valid" or clean_manifest.get("model") != "exact-lognormal-v1" or clean_manifest.get("case", {}).get("simulation", {}).get("model") != "exact-lognormal-v1":
        raise ValueError("Noise must be applied to an admitted exact-lognormal-v1 fragment set")
    clean_case = clean_manifest["case"]
    if clean_case.get("fingerprint") != fingerprint({key: value for key, value in clean_case.items() if key != "fingerprint"}):
        raise ValueError("Clean scenario fingerprint changed")
    if case.get("fingerprint") != fingerprint({key: value for key, value in case.items() if key != "fingerprint"}):
        raise ValueError("Noisy scenario fingerprint changed")
    if clean_case["replicons"] != case["replicons"] or any(clean_case["simulation"].get(key) != case["simulation"].get(key) for key in GEOMETRY_FIELDS):
        raise ValueError("Clean/noisy cases disagree on replicons or frozen fragment geometry")
    settings = case["simulation"]
    if settings["circular_read_limit"] != "one_circumference" or not 0 <= settings["minimum_breadth"] <= 1:
        raise ValueError("Unsupported source traversal or breadth policy")
    clean_hashes = {"reads_sha256": digest(clean_reads), "origins_sha256": digest(origins_path), "truth_sha256": digest(truth_path)}
    if any(clean_hashes[key] != clean_manifest.get(key) for key in clean_hashes):
        raise ValueError("Clean fragment, origin or truth checksum changed")
    truth = fasta(truth_path)
    replicons = {r["refseq_accession"]: r for r in case["replicons"]}
    if set(truth) != set(replicons) or len(replicons) != len(case["replicons"]):
        raise ValueError("Truth replicon inventory mismatch")
    if any(len(truth[name]) != replicons[name]["length_bp"] or not truth[name] or set(truth[name]) - set("ACGT") for name in truth):
        raise ValueError("Truth length/alphabet mismatch")
    reserved = ["reads.fastq.gz", "read_origins.tsv.gz", "read_audit.tsv.gz", "truth.fasta", "noisy-input.json"]
    if any((output / name).exists() for name in reserved):
        raise ValueError("Noisy outputs already exist; validate cached inputs or use a new directory")
    output.mkdir(parents=True, exist_ok=True)
    backend = BadreadBackend(profile)
    stats = {name: {"source_lengths": [], "emitted_lengths": [], "identities": [], "intervals": [],
                    "errors": Counter(), "qualities": Counter(), "quality_errors": Counter(),
                    "emitted_coverage": bytearray(replicons[name]["length_bp"])} for name in replicons}
    seen = set()
    opener = gzip.open if str(origins_path).endswith(".gz") else open
    read_partial = output / "reads.fastq.gz.partial"
    origin_partial = output / "read_origins.tsv.gz.partial"
    audit_partial = output / "read_audit.tsv.gz.partial"
    try:
        with opener(origins_path, "rt", encoding="ascii", newline="") as origins:
            origin_rows = csv.DictReader(origins, delimiter="\t")
            if origin_rows.fieldnames != ORIGIN_FIELDS:
                raise ValueError("Clean origin table header does not match the exact sampler")
            with _gzip_output(read_partial) as reads_out, _gzip_output(origin_partial) as origin_out, _gzip_output(audit_partial) as audit_out:
                writer = csv.writer(origin_out, delimiter="\t", lineterminator="\n")
                writer.writerow(ORIGIN_FIELDS)
                audit = csv.writer(audit_out, delimiter="\t", lineterminator="\n")
                audit.writerow(["read_id", "replicon", "clean_fragment_sha256", "source_length", "emitted_length",
                                "target_identity", "actual_identity", "matches", "substitutions", "insertions", "deletions",
                                "identity_seed_sha256", "error_seed_sha256", "upstream_padded_identity", "upstream_quality_identity", "global_cigar"])
                for read, origin in zip_longest(_fastq(clean_reads), origin_rows):
                    if read is None or origin is None:
                        raise ValueError("Clean FASTQ and origin table have different row counts")
                    name, fragment = read
                    if None in origin or any(value is None for value in origin.values()) or name in seen or name != origin["read_id"] or origin["replicon"] not in replicons:
                        raise ValueError("Duplicate, out-of-order or unknown read origin")
                    seen.add(name)
                    accession = origin["replicon"]
                    replicon, reference = replicons[accession], truth[accession]
                    start, size = int(origin["start_0based"]), int(origin["length"])
                    if not (0 <= start < len(reference) and size == len(fragment) and
                            min(settings["length_min"], len(reference)) <= size <= min(settings["length_max"], len(reference))):
                        raise ValueError("Source fragment coordinates/length violate the frozen cap")
                    if origin["strand"] not in ("+", "-"):
                        raise ValueError("Unknown fragment strand")
                    circular = replicon["topology"] == "circular"
                    if not circular and start + size > len(reference):
                        raise ValueError("Linear source fragment crosses a physical end")
                    expected = (reference + reference if circular else reference)[start:start + size]
                    if origin["strand"] == "-":
                        expected = reverse_complement(expected)
                    if expected != fragment:
                        raise ValueError("Clean read sequence disagrees with origin and truth")
                    identity_seed = fingerprint([ADAPTER_VERSION, "identity", clean_case["fingerprint"], name])
                    error_seed = fingerprint([ADAPTER_VERSION, "errors", profile["id"], clean_case["fingerprint"], name])
                    rng = random.Random(int(identity_seed, 16))
                    target = maximum * rng.betavariate(alpha, beta) if alpha is not None else maximum
                    emitted, quality, upstream_identity, quality_identity = backend.generate(fragment, target, error_seed)
                    if not emitted or set(emitted) - set("ACGT") or len(emitted) != len(quality) or any(not 33 <= ord(value) <= 126 for value in quality):
                        raise ValueError("Badread produced empty/non-ACGT output or invalid FASTQ quality")
                    evidence = alignment_evidence(emitted, fragment, quality, backend.align(emitted, fragment))
                    reads_out.write(f"@{name}\n{emitted}\n+\n{quality}\n")
                    writer.writerow([origin[key] for key in ORIGIN_FIELDS])
                    audit.writerow([name, accession, hashlib.sha256(fragment.encode()).hexdigest(), size, len(emitted),
                                    format(target, ".12g"), format(evidence["identity"], ".12g"), evidence["matches"],
                                    evidence["substitutions"], evidence["insertions"], evidence["deletions"], identity_seed, error_seed,
                                    format(upstream_identity, ".12g"), format(quality_identity, ".12g"), evidence["cigar"]])
                    item = stats[accession]
                    item["source_lengths"].append(size)
                    item["emitted_lengths"].append(len(emitted))
                    item["identities"].append(evidence["identity"])
                    item["errors"].update({key: evidence[key] for key in ("matches", "substitutions", "insertions", "deletions", "alignment_columns")})
                    item["qualities"].update(ord(value) - 33 for value in quality)
                    item["quality_errors"].update(evidence["quality_errors"])
                    for left, right in project_fragment_intervals(evidence["fragment_aligned_intervals"], start, size, origin["strand"], len(reference)):
                        item["emitted_coverage"][left:right] = b"\1" * (right - left)
                    stop = start + size
                    item["intervals"].append((start, min(stop, len(reference))))
                    if stop > len(reference):
                        item["intervals"].append((0, stop - len(reference)))
        if inspect_runtime(profile)["sha256"] != runtime["sha256"]:
            raise ValueError("Simulator source/model runtime changed during transformation")
        if any(digest(path) != clean_hashes[key] for path, key in ((clean_reads, "reads_sha256"), (origins_path, "origins_sha256"), (truth_path, "truth_sha256"))):
            raise ValueError("Clean input changed during noisy transformation")
        rows = [_replicon_summary(r, stats[r["refseq_accession"]], settings, profile["identity_beta_percent"]["mean"], profile["identity_beta_percent"]["sd"]) for r in case["replicons"]]
        for partial, name in ((read_partial, "reads.fastq.gz"), (origin_partial, "read_origins.tsv.gz"), (audit_partial, "read_audit.tsv.gz")):
            partial.replace(output / name)
        shutil.copyfile(truth_path, output / "truth.fasta")
        manifest = {"schema_version": 1, "case": case, "model": ADAPTER_VERSION,
                    "status": "invalid_input" if any(row["validation_holds"] for row in rows) else "valid",
                    "profile": profile, "runtime": runtime, "replicons": rows,
                    "reads_sha256": digest(output / "reads.fastq.gz"), "origins_sha256": digest(output / "read_origins.tsv.gz"),
                    "truth_sha256": digest(output / "truth.fasta"), "read_audit_sha256": digest(output / "read_audit.tsv.gz"),
                    "clean_input": {**clean_hashes, "manifest_sha256": digest(clean_manifest_path), "case_fingerprint": clean_case["fingerprint"]},
                    "rng_policy": "SHA256 canonical JSON key -> full 256-bit Python seed; Badread NumPy seeded with all eight uint32 words; identity stream excludes profile ID, error stream includes it",
                    "quality_policy": "Model-generated qualities; final identity independently recomputed against clean fragment with Edlib NW; upstream padded diagnostics retained separately",
                    "limitation": "Controlled model stress only, not empirical chemistry/basecaller calibration. Source breadth is known fragment coverage, not noisy read-alignment breadth. Tolerant assembly recovery is not scored here."}
        save(output / "noisy-input.json", manifest)
        return manifest
    except BaseException:
        for partial in (read_partial, origin_partial, audit_partial):
            partial.unlink(missing_ok=True)
        raise
