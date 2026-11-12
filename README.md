# Isolate long-read assembly benchmarks

One Nextflow workflow for **single-isolate bacterial long-read assembly**:
reference/input preparation → simulation or deposited reads → assembly →
assessment → sealed results bundle → standalone website. Hybrid and metagenomic
assembly are outside the scope.

```bash
nextflow run happykhan/assembler-benchmark-nextflow --preset quick
```

No preliminary Python commands or manual clone are needed. Quick downloads and
checks its reference, prepares pinned environments, simulates two read-length
fixtures, runs Flye and Raven, assesses the outputs and produces the report.
**Quick checks the workflow; it is excluded from scientific rankings.** It uses a
200 kb linear reference fixture, not a whole bacterial genome.

The replacement implementation now covers selectable general and diagnostic
tracks, plus import and rendering of frozen results. Small end-to-end validation
runs on Cluster 3 are complete: Quick, two general datasets, native-linear S5
and Raven read-order S7. See the [validation evidence](docs/cluster-validation-v2.md).
The [beta Standard preset](docs/beta-standard.md) now declares 55 inputs and 110
Flye/Raven outcomes across five seeds, whole-genome GC strata and error-free
read-length/coverage/plasmid-depth contrasts. The full scientific protocol remains
under review. Implemented functionality and verified scientific runs are different;
see [replacement verification](docs/nextflow-replacement-verification.md).

Inspect available choices with `--list` and command help with `--help`.
`--plan_only` freezes a selection without preparing inputs; `--prepare_only`
prepares the selected inputs without launching assemblies. S7 requires its
verified original source directories under `--diagnostic_source_dir`.

## Choose what to run

| Selection | Purpose |
| --- | --- |
| `--preset quick` | Small simulated workflow check; the default |
| `--preset standard` | Beta simulated whole-genome panel; 55 inputs, 110 default outcomes |
| `--track general --preset standard` | Frozen Wick/Holt 50-dataset general comparison |
| `--track diagnostic --preset standard --groups S5` | Selected controlled diagnostic family |
| `--track real --preset standard --cases johnson-atcc25922-full` | Admitted real-data small-plasmid pilot |
| `--import_bundle /path/to/frozen/bundle` | Verify, admit and render existing results; no assembly |

For the frozen general set, the default four reported workflows are Flye, Raven,
Plassembler and Miniasm + Minipolish: 50 datasets × 4 = 200 slots. The raw Miniasm
phase is retained as an intermediate of the polished workflow. General results
and diagnostic endpoints remain separate.

```bash
# General comparison: documented execution entry point, pending protocol approval
nextflow run happykhan/assembler-benchmark-nextflow \
  --track general --preset standard --outdir results/general --run_id general

# One diagnostic family
nextflow run happykhan/assembler-benchmark-nextflow \
  --track diagnostic --preset standard --groups S5 \
  --outdir results/linear --run_id linear
```

Diagnostic selectors are comma-separated IDs or aliases:

| ID | Alias | Family |
| --- | --- | --- |
| S1 | `plasmids` | Exact recovery controls and native complements |
| S2 | `coverage` | Relative plasmid coverage |
| S3 | `reproducibility` | Repeats and thread settings |
| S4 | `read-length` | Small plasmids and read lengths |
| S5 | `linear` | Linear plasmids and terminal repeats |
| S6 | `errors` | Historical noisy-read evidence; **new runs deferred** |
| S7 | `read-order` | Output agreement across read orders |

Use `--cases` and `--assemblers` for narrower selections. Definitions pin tool
versions and resources; [adding an assembler](docs/adding-assemblers.md) describes
the registry and adapter contract. The proposed broader five-group scientific
panel remains a protocol under review, distinct from these preserved S1–S7 IDs.

## Review a plan without running science

```bash
nextflow run happykhan/assembler-benchmark-nextflow \
  --track diagnostic --preset standard --groups S5 \
  --plan_only -profile native_tools --outdir results/plan-s5

nextflow run happykhan/assembler-benchmark-nextflow \
  --track general --preset standard \
  --plan_only -profile native_tools --outdir results/plan-general
```

These commands freeze and validate metadata only. They do not download scientific
inputs, simulate reads, assemble or assess sequences. `native_tools` avoids
software provisioning for this review path and requires an available Python
3.11 or later. The output includes `selected-plan.json` and its preparation
receipt. A frozen plan can subsequently be supplied with `--plan`; it cannot be
combined with new selection options.

## Render existing results without rerunning assemblies

```bash
nextflow run happykhan/assembler-benchmark-nextflow \
  --import_bundle /path/to/frozen/bundle \
  --outdir results/import -profile native_tools
```

The import verifies the complete file inventory and SHA-256 bindings, retains
source bytes and renders the website from sealed evidence. It does not invoke the
old controller, query a scheduler, rescore sequences or rerun an assembler. Both
historical frozen bundles and native Nextflow bundles are supported. Historical
S5, S6 and S7 evidence remains available, including supplementary results and the
separate S7 reference verdict.

## Execution profiles

Linux x86-64 requires Nextflow 25.10.2 or later and a compatible Java runtime.
The default software runtime is [Pixi](https://pixi.sh) 0.73.0 or later.
Software and execution profiles are independent:

```bash
# Local execution and automatically prepared Pixi environments
nextflow run happykhan/assembler-benchmark-nextflow --preset quick -profile pixi

# Cluster 3: Slurm with Pixi, or Slurm with Singularity
nextflow run happykhan/assembler-benchmark-nextflow --preset quick -profile bmrc,pixi
nextflow run happykhan/assembler-benchmark-nextflow --preset quick -profile bmrc,singularity

# Workstation container profile
nextflow run happykhan/assembler-benchmark-nextflow --preset quick -profile docker
```

Generic Slurm sites use `slurm,pixi` or `slurm,singularity` with their own site
configuration. `apptainer` is also provided. Choose exactly one software runtime.
Container profiles share a digest-pinned Linux Pixi image and provision locked
scientific environments on the shared filesystem. The first online run needs
network access. Docker configuration is provided; Docker execution has not been
verified on Cluster 3. Pixi and Singularity Quick execution have been verified;
see [runtime evidence](docs/native-entry-verification.md).

The queue capacity is 1,000. Genuine software/resource failures are recorded
without automatic assembler retries. Use `-resume` to reuse completed tasks;
reporting changes have separate cache keys from assembly. Pin `-r <commit-or-tag>`
for reproducibility, or deliberately use `-latest` to fetch updated code.

## Outputs and interpretation

A normal run writes:

- `selected-plan.json` and `environment-preparation.json`: selection and software receipts.
- `bundle/`: checksummed JSON/TSV, original execution evidence, retained assemblies
  and graphs, prepared presentation metadata, and a standalone report.
- `website/`: presentation pages, interactive saved graph models, figures and TSV downloads.
- `nextflow-trace.tsv`: scheduler/runtime evidence.

The bundle is the portable scientific record; the website is a separate view.
Neither needs a website deployment. General performance and aggregate pages are
separate from diagnostic scenarios. Missing measurements stay missing. Execution,
input preparation and assessment errors never establish sequence absence.

General completion uses the fixed Wick longest-single-alignment criterion against
tripled references, at 99%, with uncapped contiguity. Diagnostic exact-copy scores,
real-pilot paper rules and repeatability/output agreement have their own endpoints.
In particular, S7 secondary reference pass/fail cannot decide its agreement verdict.
Time and process-tree RAM are reported separately from scientific measurements;
downloads, software provisioning, simulation and scheduler waiting are excluded
from workflow time. Shared pages can be counted more than once in sampled RSS.

For offline execution, populate the exact checked reference/read caches and
locked software environments in advance, then use `--offline`,
`--reference_dir /shared/references` and `--read_cache /shared/reads`.
Optional administrative preparation helpers are documented in
[reference admission](docs/reference-admission.md). They are not prerequisites for
normal online Nextflow runs. Missing or modified cached inputs stop admission.

## Structure, verification and cleanup

`main.nf` connects modules in `modules/local/preparation.nf`, `execution.nf` and
`reporting.nf`. Python helpers in `benchlib/` handle pinned planning, input
admission, adapters and native results; `diagnostic_core/` preserves diagnostic
scientific methods; `reporting/` and `website/` produce the standalone website.
Frozen metadata live in `assets/general/` and `assets/diagnostics/`.

```bash
python3 -m unittest discover -s tests -v
```

[Replacement verification](docs/nextflow-replacement-verification.md) distinguishes
metadata/render tests from scientific execution. Other evidence includes the
[Standard baseline](docs/standard-baseline.md), its
[independent assessment audit](docs/assessment-diagnosis.md), the
[real small-plasmid pilot](docs/real-small-plasmid-pilot.md), and the
[literature review](docs/literature-review.md).

Nothing is purged automatically. Keep work for `-resume` and retain sealed
outputs before considering cleanup. The optional
[guarded launcher](bin/launch.py) creates ownership markers used by
`bin/cleanup.py`; that tool defaults to a dry run and refuses unmarked direct
Nextflow work directories. Direct runs use Nextflow's own reviewed
[`clean` command](https://www.nextflow.io/docs/latest/reference/cli.html#clean).
Shared reference/read caches and active inputs are not automatically deleted.
