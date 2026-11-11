# Selectable benchmark catalogue

The project covers single-isolate bacterial long-read assembly. Quick is a
workflow check and is excluded from headline scientific comparisons. Standard
remains unadmitted until its panel, controls and measurements are curated and
validated. There are no hybrid or metagenomic tracks.

| Group ID | Purpose | Current runnable cases |
| --- | --- | --- |
| `plasmids` | Recovery, copy depth, size and separation of plasmid molecules. | None admitted yet. |
| `gc-composition` | Separate intrinsic composition effects from sequencing bias. | None admitted yet. |
| `repeats-structure` | Assembly through repeated sequence and genome structures. | None admitted yet. |
| `read-quality` | Coverage, length distribution and read quality/sampling. | `quick-baseline`, `quick-bimodal`. |
| `reproducibility` | Distinguish repeated execution, read order and independent sampling. | None admitted yet. |

Quick's two cases use the same 200,000-base linear reference fixture and the same
6,000,000-base budget. The bimodal case changes the short/long base mixture;
base proportions and realised read-count proportions are recorded separately.
This does not establish a whole-genome or realistic Nanopore benchmark.

Inspect the catalogue without downloading data or scheduling jobs:

```bash
python3 bin/plan.py --list
```

Create a frozen selection:

```bash
python3 bin/plan.py --preset quick --groups read-quality \
  --cases quick-bimodal --assemblers flye,raven --out selected-plan.json
```

Aliases resolve to immutable assembler-version IDs in the plan. The plan retains
exact case/assembler slots, reference accessions and source checksums, selected
environment declarations and locks, declared resource policy and its canonical
SHA256. Changed sources, unknown selections, duplicate versions and extra or
missing slots fail validation before scheduling. An existing plan is never
silently overwritten. Requested groups without admitted cases are explicitly
rejected rather than silently omitted.

Validate the saved plan against the current source files:

```bash
python3 bin/plan.py --validate selected-plan.json --out admitted-plan.json
```

The declared defaults are two assembly CPUs, 30 minutes, 16 GB for Flye and 4 GB
for Raven, with queue capacity 1,000. These are planned allocations, not observed
measurements. The workflow must apply them or freeze an explicit updated policy;
measured process-tree resource use remains separate in the result evidence.
