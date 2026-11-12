# Isolate long-read assembly benchmarks

A separate Nextflow DSL2 project for selectable **single-isolate bacterial
long-read assembly** benchmarks. Simulated data come first. Hybrid and metagenomic
workflows are outside this project's scope.

## Current development slice

Quick runs two read-length cases through actual Badread simulation, Flye and Raven,
Wick-style assessment, checksummed JSON/TSV export and a standalone HTML report.
Both cases receive exactly 6,000,000 sequenced bases. The bimodal case allocates
half the bases to each length mode; read-count proportions are measured separately.
Read modes are deterministically interleaved.

**Quick checks the workflow, not assembler performance.** Its reference is the
first 200,000 bases of the checksummed *Bacillus subtilis* 168 chromosome
NC_000964.3, treated as a linear fixture. It is neither a whole-genome benchmark
nor part of a scientific ranking. Uniform error-free simulation does not model
Nanopore sequencing bias. A small Standard whole-genome baseline is now admitted
for two checked chromosomes; the full scientific panel remains unadmitted.

The five agreed groups for Standard are plasmids, GC/composition, repeats/genome
structure, read quality/sampling, and reproducibility. Currently only the Quick
read-quality fixtures and the two-reference Standard baseline are implemented.
Real-data admission follows the simulated end-to-end implementation.

## Run with Nextflow

Requirements: Nextflow 25.10.2 with Java 17–25, and one configured runtime. The
locked Pixi environment supplies Java 17 and the scientific tools on Linux x86-64.
Install Nextflow separately using its [official instructions](https://www.nextflow.io/docs/latest/install.html).

Clone the repository and prepare the selected cases and software once:

```bash
git clone https://github.com/happykhan/assembler-benchmark-nextflow.git
cd assembler-benchmark-nextflow

pixi run --locked --manifest-path environments/pixi.toml python bin/plan.py \
  --preset quick --out results/quick-001/selected-plan.json
pixi run --locked --manifest-path environments/pixi.toml python bin/prepare-environments.py \
  --plan results/quick-001/selected-plan.json \
  --out results/quick-001/environment-preparation.json
```

**Run the pipeline with Nextflow:**

```bash
nextflow run . -profile local,pixi \
  --plan results/quick-001/selected-plan.json \
  --run_id quick-001 --outdir results/quick-001 \
  -work-dir work/quick-001
```

Nextflow runs reference preparation, simulation, parallel assembly, assessment
and report export. Python scripts implement individual tasks and the preparation
helpers; they do not replace the Nextflow workflow.

The current release requires a prepared `--plan` and locked environments. A bare
`nextflow run . --preset quick` does not yet perform those setup steps. Run from
the cloned checkout so prepared Pixi environments and pipeline sources share the
same location. If Java is supplied by Pixi, prefix the Nextflow command with
`pixi run --locked --manifest-path environments/pixi.toml`.

For Cluster 3, replace `local,pixi` with `bmrc,pixi`. Generic Slurm users use
`slurm,pixi` plus their site account/partition configuration. Add `-resume` to the
same Nextflow command to reuse completed tasks. Queue capacity is 1,000; failed
assemblers are not automatically retried. Use distinct run IDs and output/work
directories for separate attempts.

Select existing cases and assemblers independently:

```bash
pixi run --locked --manifest-path environments/pixi.toml python bin/plan.py \
  --cases quick-bimodal --assemblers raven-1.8.3 \
  --out results/selected-001/selected-plan.json
```

Prepare that plan's environments, then pass it to `nextflow run . --plan ...` as
above. `bin/plan.py --groups read-quality` selects the implemented Quick group.
Unsupported selections fail rather than silently running a different panel.
Source code, input bytes and the dependency lock participate in resume keys.
Purging work prevents resume.

Docker and Apptainer profiles are provided separately from executor profiles.
They remain unadmitted until each selected assembler has a digest-pinned image
in the registry. The pipeline rejects these profiles before scheduling when an
image is absent; these container paths have not yet been integration-tested. The verified initial
runtime is Linux Pixi on Slurm. Do not combine multiple runtime profiles.

## Prepare references before an offline run

Download and validate the exact source archive on a machine with network access:

```bash
python3 bin/prepare-reference.py --registry assets/references.json \
  --id bsub-168-quick --reference-dir references \
  --out references/quick-reference.fasta --metadata references/quick-reference.json
```

Copy the `references` directory to the execution host, then add `--offline` and
`--reference_dir /shared/references` to the Nextflow command.
Offline preparation rechecks the source checksum; missing or modified files stop
the workflow. Online mode runs the same preparation stage on the compute executor.
Python preparation requires Python 3.11 or later; the Pixi environment provides it.

## Outputs and cleanup

`results/<run>/bundle/index.html` is a standalone report. Beside it are
`results.tsv`, `results.json`, final assemblies/available graphs, evidence and
`manifest.json`. The manifest binds every retained file by SHA256 and records the
exact expected case×assembler slots. The website can ingest the bundle without
running Nextflow. No website publication is required to use the report.

Completeness, measured identity/indels, execution state, time and RAM remain
separate. Structural correctness is explicitly unmeasured in this first slice.
Software errors, infrastructure errors and assessment errors are distinguished;
none establishes sequence absence. Assembly time includes verification; downloads,
environment provisioning, simulation and scheduler waiting are excluded. RAM is sampled process-tree RSS,
which can double-count shared pages; mapper RAM is reported separately.

The custom cleanup tool below applies to runs created by the optional guarded
launcher, which writes ownership markers. Direct Nextflow runs do not create
those markers; the tool deliberately refuses to delete their work directories.
Retain direct-run work for `-resume`, and review Nextflow's own
[`clean` command](https://www.nextflow.io/docs/latest/reference/cli.html#clean)
when deciding what to remove.

For a guarded-launcher run, inspect cleanup after a complete, verified export:

```bash
python3 bin/cleanup.py --bundle results/quick-001/bundle --work-dir work/quick-001
```

This defaults to a dry run. Actual deletion additionally requires
`--apply --confirm-run-id quick-001`. It removes only the marked work directory,
blocks active runs, verifies retained evidence and keeps the shared reference
cache and final report. No cleanup is performed automatically.

## Optional guarded launcher

This convenience command prepares the plan and environments, then calls
`nextflow run main.nf` itself. It also holds a lifecycle lock, creates ownership
markers for the custom cleanup tool and independently checks the final bundle.

```bash
pixi run --locked --manifest-path environments/pixi.toml python bin/launch.py \
  --run-id quick-guarded-001 \
  --outdir results/quick-guarded-001 --work-dir work/quick-guarded-001 \
  -- -profile local,pixi
```

Launcher selections such as `--preset`, `--cases` and `--assemblers` go before
the `--` separator; Nextflow options go after it. Choose either entry point when
starting a run. The guarded launcher does not adopt a non-empty work directory
created by a direct Nextflow run.

## Development and evidence

```bash
python3 -m unittest discover -s tests -v
```

Scientific dependencies are pinned in `environments/pixi.toml` and fully resolved
in `environments/pixi.lock`. `assets/assemblers.json` lists the admitted initial
versions; adapters validate actual executable versions before running. Each immutable version has its own locked named environment. Adding a new
version of an existing adapter requires a registry entry and pinned environment,
without editing the pipeline; adding a new tool also requires a tested adapter.
Arbitrary user-supplied commands are not accepted. See
[adding assemblers](docs/adding-assemblers.md). Standard-panel expansion remains
subsequent work.

See [the literature review](docs/literature-review.md) for Wick/Holt, recent isolate
long-read studies, multi-assembler workflows and engineering precedents, and
[development verification](docs/verification.md) for actual run evidence.

## Inspect and freeze a selection

```bash
python3 bin/plan.py --list
python3 bin/plan.py --cases quick-bimodal --assemblers flye-2.9.6,raven-1.8.3 --out selected-plan.json
```

Pass this plan to `nextflow run . --plan selected-plan.json` after preparing its
environments. The optional launcher can also accept `--plan selected-plan.json`.
Plans bind exact version IDs, case/reference metadata, manifest/lock hashes,
resource policy and expected result slots. Typos, duplicate versions, changed
plans and unadmitted groups stop before assembly scheduling. A dedicated first
Nextflow task independently validates the plan before any reference preparation.

The [Standard proposal](docs/standard-panel-design.md) describes the larger
five-group panel. Two references are now admitted for a small whole-genome
baseline; the remaining candidates and scenario contrasts are not admitted. See
[reference admission](docs/reference-admission.md) and
[the Standard baseline](docs/standard-baseline.md).

To prepare software before using compute nodes without network access, freeze a
plan and run `python bin/prepare-environments.py --plan selected-plan.json --out environment-preparation.json`
on the shared execution filesystem. Reference preparation remains a separate
checksummed cache step. Environment provisioning is recorded separately from
assembly/assessment time.

## Interpret the completion criterion

The original `incomplete` outcome means that no single alignment spans 99% of
the reference. It is a contiguity endpoint, separate from total reference
coverage. The report now states this explicitly and shows assembly contig counts.
Identity and maximum indel describe the selected longest alignment, rather than
every contig in the assembly.

An [independent audit of the first Standard baseline](docs/assessment-diagnosis.md)
reproduced all four original scores with a different aligner. The saved outputs
cover over 99% of each reference across multiple contigs; some Bacillus contigs
also have structural discontinuities. The [workflow review](docs/fragmentation-review.md)
records input coverage, read-spanning checks and configuration concerns without
claiming an experimentally established cause. No assembly or simulation was rerun.

## Run the admitted Standard baseline

The baseline uses the full native circular chromosomes of *B. subtilis* 168 and
*L. lactis* IL1403, with exact 30× error-free read budgets and four result slots
for the initial two assembler versions. It is baseline validation, excluded from
headline comparisons; structural correctness remains unmeasured.

```bash
pixi run --locked --manifest-path environments/pixi.toml python bin/plan.py \
  --preset standard --out results/standard-001/selected-plan.json
pixi run --locked --manifest-path environments/pixi.toml python bin/prepare-environments.py \
  --plan results/standard-001/selected-plan.json \
  --out results/standard-001/environment-preparation.json
nextflow run . -profile bmrc,pixi \
  --plan results/standard-001/selected-plan.json \
  --run_id standard-001 --outdir results/standard-001 \
  -work-dir work/standard-001
```

Online mode downloads and validates the admitted source archives. For offline
nodes, run the preparation command above once for each ID `bsub-168-whole` and
`llactis-il1403-whole`, copy the cache to the shared filesystem, and add `--offline`.
Whole preparation rejects changed hashes, molecule inventories, truncation and
Quick fragments. Raw sources and admission metadata remain retained.
