"""Expand the pinned inventory into finite baseline and relative-depth scenarios."""

import copy
import math
import re

from .common import ROOT, fingerprint, load

LABELS = {
    "GCF_000005845.2": "MG1655",
    "GCF_000258145.1": "W",
    "GCF_000010385.1": "SE11",
    "GCF_024397815.1": "Ecl8",
    "GCF_000016305.1": "MGH78578",
}


def plan(config):
    if config.get("linear_panel"):
        from .linear_cases import plan_linear
        return plan_linear(config)
    inventory = load(ROOT / "references/panel.json")["assemblies"]
    selected = config["references"]
    minimum = config.get('minimum_plasmid_bp')
    if minimum is not None and (type(minimum) is not int or minimum < 1):
        raise ValueError('Minimum plasmid size must be a positive integer')
    known = {entry["assembly"]["assembly_accession"] for entry in inventory}
    if set(selected) - known:
        raise ValueError("Unknown reference accession in configuration")
    result = []
    for entry in inventory:
        assembly = entry["assembly"]
        accession = assembly["assembly_accession"]
        if accession not in selected:
            continue
        if assembly["selection_status"] != "preferred_candidate":
            raise ValueError(f"Reference is held, not a preferred candidate: {accession}")
        replicons = entry["replicons"]
        chromosome = [r for r in replicons if r["molecule_type"] == "chromosome"]
        native_plasmids = [r for r in replicons if r["molecule_type"] == "plasmid"]
        plasmids = [r for r in native_plasmids if minimum is None or r['length_bp'] >= minimum]
        if len(chromosome) != 1:
            raise ValueError("Pilot requires one chromosome")
        subsets = [("chromosome", [], "Chromosome only")]
        subsets += [(r["replicon_name"].lower(), [r], "Chromosome + " + r["replicon_name"]) for r in plasmids]
        if len(plasmids) > 1:
            subsets.append(("large" if minimum is not None else "native", plasmids,
                            f"Chromosome + all plasmids ≥{minimum:,} bp" if minimum is not None else "Chromosome + all native plasmids"))
        for suffix, subset, title in subsets:
            case = {
                "id": f"s1-{LABELS[accession].lower()}-{suffix}",
                "title": f"{LABELS[accession]} · {title}",
                "category": "S1",
                "assembly_accession": accession,
                "organism": assembly["organism"],
                "truth_type": "native_complement" if len(subset) == len(native_plasmids) else "derived_subset",
                "replicons": chromosome + subset,
                "simulation": config["simulation"],
                "profile_id": config["profile_id"],
            }
            case["fingerprint"] = fingerprint(case)
            result.append(case)
    for target in config.get("coverage_panel", {}).get("targets", []):
        source = next((case for case in result if case["category"] == "S1" and case["assembly_accession"] == target["assembly"]
                       and [r["refseq_accession"] for r in case["replicons"] if r["molecule_type"] == "plasmid"] == [target["plasmid"]]), None)
        if source is None:
            raise ValueError("Coverage targets must identify one native plasmid in a selected reference")
        for ratio in config["coverage_panel"]["ratios"]:
            if ratio <= 0:
                raise ValueError("Coverage ratios must be positive")
            case = copy.deepcopy(source)
            label = format(ratio, "g")
            case["id"] = source["id"].replace("s1-", "s2-", 1) + "-depth-" + label.replace(".", "p")
            case["title"] = source["title"] + f" · {label}× relative depth"
            case["category"] = "S2"
            case["simulation"]["plasmid_relative_depth"] = ratio
            case["fingerprint"] = fingerprint({key: value for key, value in case.items() if key != "fingerprint"})
            result.append(case)
    result.extend(read_length_cases(config, result))
    result.extend(noisy_cases(config, result))
    if len({case["id"] for case in result}) != len(result):
        raise ValueError("The configuration produces duplicate scenario identifiers")
    categories = config.get("scenario_categories")
    if categories is not None:
        if not categories or set(categories) - {"S1", "S2", "S4", "S6"}:
            raise ValueError("Select supported nonempty scenario categories")
        result = [case for case in result if case["category"] in categories]
        if not result:
            raise ValueError("The configuration selects no scenarios")
    selected_ids = config.get('scenario_ids')
    if selected_ids is not None:
        if not isinstance(selected_ids, list) or not selected_ids or any(not isinstance(value, str) for value in selected_ids) or len(set(selected_ids)) != len(selected_ids):
            raise ValueError('Scenario selection requires unique identifiers')
        if set(selected_ids) - {case['id'] for case in result}:
            raise ValueError('Scenario selection contains unknown or excluded cases')
        result = [case for case in result if case['id'] in selected_ids]
    return result


def read_length_cases(config, baseline):
    """Vary whole-input read lengths for a small plasmid alone and in its complement."""
    panel = config.get("read_length_panel")
    if panel is None:
        return []
    profiles = panel.get("profiles", [])
    if not panel.get("targets") or not profiles:
        raise ValueError("Read-length panels require targets and profiles")
    keys = {"length_mean", "length_sd", "length_min", "length_max"}
    for profile in profiles:
        if not re.fullmatch(r"[a-z][a-z0-9-]*", profile.get("id", "")):
            raise ValueError("Read-length profiles require a simple lower-case identifier")
        if set(profile) != keys | {"id", "title"}:
            raise ValueError("Read-length profiles must declare all four length settings, id and title")
        if any(isinstance(profile[k], bool) or not isinstance(profile[k], (int, float))
               or not math.isfinite(profile[k]) or profile[k] < (0 if k == "length_sd" else 1) for k in keys):
            raise ValueError("Read-length settings must be finite and positive; SD may be zero")
        if any(not isinstance(profile[k], int) for k in ("length_min", "length_max")):
            raise ValueError("Read-length bounds must be whole numbers of bases")
        if not isinstance(profile["title"], str) or not profile["title"].strip():
            raise ValueError("Read-length profiles require a readable title")
        if profile["length_min"] > profile["length_max"]:
            raise ValueError("Minimum read length must not exceed maximum read length")
    result = []
    for target in panel["targets"]:
        candidates = [case for case in baseline if case["category"] == "S1"
                      and case["assembly_accession"] == target["assembly"]]
        source = next((case for case in candidates if [r["refseq_accession"] for r in case["replicons"]
                       if r["molecule_type"] == "plasmid"] == [target["plasmid"]]), None)
        native = next((case for case in candidates if case["truth_type"] == "native_complement"), None)
        if source is None or native is None:
            raise ValueError("Read-length targets must identify a native plasmid in a selected reference")
        if config["simulation"]["circular_read_limit"] != "one_circumference":
            raise ValueError("The S4 panel requires one-circumference clipping")
        for mode in panel.get("contexts", ["individual", "native"]):
            if mode not in {"individual", "native"}:
                raise ValueError("Read-length context must be individual or native")
            for profile in profiles:
                case = copy.deepcopy(source if mode == "individual" else native)
                case["id"] = case["id"].replace("s1-", "s4-", 1) + "-length-" + profile["id"]
                case["title"] += " · " + profile["title"]
                case["category"] = "S4"
                case["read_length_profile"] = profile["id"]
                case["small_plasmid_accession"] = target["plasmid"]
                case["simulation"].update({key: profile[key] for key in keys})
                case["fingerprint"] = fingerprint({key: value for key, value in case.items() if key != "fingerprint"})
                result.append(case)
    return result


def find_case(config, case_id):
    return next((c for c in plan(config) if c["id"] == case_id), None) or _missing(case_id)


def _missing(case_id):
    raise ValueError(f"Unknown scenario: {case_id}")


def noisy_cases(config, baseline):
    panel = config.get("noisy_panel")
    if not panel:
        return []
    targets, seeds, profiles = panel["targets"], panel["seeds"], panel["profiles"]
    if not targets or len(set(targets)) != len(targets) or not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("Noisy panels require unique targets and seeds")
    if any(type(seed) is not int or seed < 0 for seed in seeds):
        raise ValueError("Fragment seeds must be nonnegative integers")
    if not profiles or len({p["id"] for p in profiles}) != len(profiles):
        raise ValueError("Noisy profiles must be nonempty and unique")
    result = []
    for target in targets:
        source = next((case for case in baseline if case["id"] == target and case["category"] == "S1"), None)
        if source is None:
            raise ValueError("Noisy targets must identify a selected S1 reference subset")
        for seed in seeds:
            for profile in profiles:
                if profile["id"] not in {"matched-exact", "generic-stress", "ont2023-shaped"}:
                    raise ValueError("Unsupported noisy profile identifier")
                expected={"matched-exact":(None,"placeholder-q40"), "generic-stress":("random","ideal"), "ont2023-shaped":("nanopore2023","nanopore2023")}[profile["id"]]
                if (profile.get("error_model"),profile.get("qscore_model")) != expected:
                    raise ValueError("Profile label does not match its frozen error/quality package")
                if profile["id"] == "matched-exact" and ("identity_beta_percent" in profile or config["simulation"]["fastq_phred"] != 40):
                    raise ValueError("Matched exact controls require the declared Q40 placeholder without an error distribution")
                case = copy.deepcopy(source)
                case["id"] = target.replace("s1-", "s6-", 1) + f'-seed-{seed}-' + profile["id"]
                case["title"] += f' · {profile["id"]} · seed {seed}'
                case["category"] = "S6"
                case["source_case_id"] = source["id"]
                frozen_source = panel.get("frozen_sources", {}).get(source["id"])
                if frozen_source is not None:
                    case["frozen_source"] = copy.deepcopy(frozen_source)
                case["simulation"].update(model="matched-error-v1", seed=seed)
                case["error_profile"] = copy.deepcopy(profile)
                case["fingerprint"] = fingerprint({key:value for key,value in case.items() if key != "fingerprint"})
                result.append(case)
    return result
