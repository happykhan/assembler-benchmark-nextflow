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

On Linux x86-64, install Nextflow 25.10.2 or later, a compatible Java runtime,
and [Pixi](https://pixi.sh). Then run:

```bash
nextflow run happykhan/assembler-benchmark-nextflow --preset quick
```

**No Python setup commands or manual clone are required.** The pipeline freezes
and validates the selection, installs the locked tooling and assembler
environments, downloads and checks the reference, simulates reads, runs the
assemblers, assesses them and exports the standalone report. The first run needs
network access and takes longer while software is installed. Outputs default to
`results/quick/bundle/index.html`; references are cached in the launch directory.
Nextflow keeps its downloaded pipeline and prepared environments in its asset cache.

Runtime and execution profiles are independent, following the usual
[nf-core convention](https://nf-co.re/docs/running/configuration/configuration-options):

```bash
# Explicit Pixi runtime on a workstation (the default)
nextflow run happykhan/assembler-benchmark-nextflow --preset quick -profile pixi

# Cluster 3: Pixi software, Slurm execution
nextflow run happykhan/assembler-benchmark-nextflow --preset quick -profile bmrc,pixi

# Cluster 3: Singularity software runtime, Slurm execution
nextflow run happykhan/assembler-benchmark-nextflow --preset quick -profile bmrc,singularity

# Docker workstation (profile provided; not verified on Cluster 3)
nextflow run happykhan/assembler-benchmark-nextflow --preset quick -profile docker
```

Singularity, Apptainer and Docker use the same digest-pinned Linux Pixi runtime
image. Locked scientific environments are installed automatically on the shared
pipeline filesystem and used inside that container; they are not baked into the
image. Container profiles require the container engine, without a host Pixi
installation. They need network access for initial image and package preparation.
Software provisioning runs on the submission host before compute tasks are
released. Do not combine multiple runtime profiles.

Generic Slurm sites use `slurm,pixi` or `slurm,singularity` plus their site
account/partition configuration. `apptainer` is also provided. `native_tools` is
an advanced profile for externally prepared, version-matched tools; it performs
no software installation. See [runtime verification](docs/native-entry-verification.md)
for tested paths and limitations.

Select cases and versions directly:

```bash
nextflow run happykhan/assembler-benchmark-nextflow --preset quick \
  --cases quick-bimodal --assemblers raven-1.8.3 \
  --outdir results/selected-001 --run_id selected-001
```

`--groups read-quality` selects the implemented Quick group. Unsupported
selections fail before assembly scheduling. Add `-resume` to reuse completed
tasks; use `-latest` when deliberately fetching an updated pipeline, or
`-r <commit-or-tag>` to pin one. Source code, input bytes and the dependency lock
participate in resume keys. A changed selection requires a new output directory.
Queue capacity is 1,000; failed assemblers are not automatically retried.
Purging work prevents resume.

`selected-plan.json` and `environment-preparation.json` are written beside the
bundle. The bundle retains the plan and runtime receipt with checksums. Advanced
users can pass an existing frozen selection with `--plan`; do not combine that
with selection options. A local development checkout runs identically with
`nextflow run . --preset quick`.

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

Pass this plan to `nextflow run . --plan selected-plan.json`; software is prepared
automatically. The optional launcher can also accept `--plan selected-plan.json`.
Plans bind exact version IDs, case/reference metadata, manifest/lock hashes,
resource policy and expected result slots. Typos, duplicate versions, changed
plans and unadmitted groups stop before assembly scheduling. A dedicated first
Nextflow task independently validates the plan before any reference preparation.

The [Standard proposal](docs/standard-panel-design.md) describes the larger
five-group panel. Two references are now admitted for a small whole-genome
baseline; the remaining candidates and scenario contrasts are not admitted. See
[reference admission](docs/reference-admission.md) and
[the Standard baseline](docs/standard-baseline.md).

For nodes without network access, prepare the reference cache in advance and
make the selected locked software environments available on the shared execution
filesystem. Optional preparation helpers support this administrative task;
they are not required for normal online runs.

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
nextflow run happykhan/assembler-benchmark-nextflow --preset standard \
  -profile bmrc,pixi --outdir results/standard-001 --run_id standard-001
```

Online mode downloads and validates the admitted source archives. For offline
nodes, run the preparation command above once for each ID `bsub-168-whole` and
`llactis-il1403-whole`, copy the cache to the shared filesystem, and add `--offline`.
Whole preparation rejects changed hashes, molecule inventories, truncation and
Quick fragments. Raw sources and admission metadata remain retained.
