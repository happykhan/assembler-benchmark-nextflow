# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

The existing implementation uses Nextflow for scientific execution, Python for
current-result storage/report rendering, and self-contained HTML/CSS/JavaScript.
The optional website consumes current packages; it does not execute scientific
tools or calculate new sequence measurements.

## Product Purpose

A general single-isolate bacterial genome assembly benchmark covering short and
long reads, with real and simulated datasets. Readers compare measured behaviour
across declared dataset collections and focused scientific questions.

## Operating Context

Users select cases, scenarios or collections through a common Nextflow catalogue.
Shared preparation supports connected nodes and preloaded offline caches. Cases
produce independently understandable current-result packages; aggregation and
website generation remain separate. Validation uses small workflows rather than
a full scientific panel.

## Capabilities and Constraints

- Two primary sections: **Broad benchmarks** and **Targeted scenarios**.
- Five scenario families: plasmids, GC and composition, repeats and structure,
  read quality and sampling, and reproducibility. Plasmids are one family.
- Read technology and real/simulated source are independent properties; workflow
  eligibility is explicit for each case.
- Distinguish measured outcomes, execution failure, assessment failure, not
  applicable and not run. Failed measurement never establishes sequence absence.
- Comparisons show question, conditions, dataset scope, focused plots and a compact
  table. Individual results hold metrics, methods, configuration and available
  graphs, saved alignments and downloads.
- Keep one current result per case/configuration, with scientific repeats only
  where designed. Reruns replace current even when they fail; upgrades record
  actual versions without an operational history or version selector.
- No overall winner score or homepage full of plots.
- Standalone packages use relative paths and shared dependency closure. Public
  payloads exclude large reads, raw logs and bulky scientific evidence.
- Old formats, URLs and historical import parity are not requirements of this
  refactor. Unrelated stored research data is not deleted.

## Evidence on Hand

The user-approved design is in `docs/refactor-specification.md`. The common
catalogue/output contract are in `benchlib/catalogue.py` and
`benchlib/current_results.py`. Software fixtures are explicitly distinguished
from scientific findings. The inherited typeface, neutral light/dark palette and notices are preserved in
`reporting/current_assets/`. The new navigation and comparison surfaces retain
those reading conventions while replacing the data architecture.

## Product Principles

1. Scientific output succeeds independently of optional website generation.
2. Share inputs and case packages instead of duplicating work across groups.
3. Keep methods, units, eligibility and failure classes explicit.
4. Present supplied measurements without manufacturing missing results.
5. Keep current results portable, understandable and easy to compare.
