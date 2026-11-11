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
Nanopore sequencing bias. Standard is deliberately rejected until its scientific
panel is curated and admitted.

The five agreed groups for Standard are plasmids, GC/composition, repeats/genome
structure, read quality/sampling, and reproducibility. Currently only the Quick
read-quality fixtures are implemented. Real-data admission follows the simulated
end-to-end implementation.

## Run Quick

Requirements: Nextflow 25.10.2 with Java 17–25, and one configured runtime. The
locked Pixi environment supplies Java 17 and the scientific tools on Linux x86-64.
Install Nextflow separately using its [official instructions](https://www.nextflow.io/docs/latest/install.html).

```bash
pixi install --locked --manifest-path environments/pixi.toml
pixi run --locked --manifest-path environments/pixi.toml python bin/launch.py \
  --run-id quick-001 --outdir results/quick-001 --work-dir work/quick-001 \
  -- -profile local,pixi
```

The launcher freezes and validates the run plan, prepares selected locked Pixi
environments serially, creates owned work markers and prevents concurrent cleanup.
Compute tasks use already prepared environments with installation disabled; this
does not throttle assembler jobs. Setup receipts are saved beside the report. For
Cluster 3, use `-profile bmrc,pixi`; generic Slurm users use `slurm,pixi` plus their
site account/partition configuration. Queue capacity is 1,000. No failed assembler
is automatically retried. Use a distinct run ID/output/work directory for a new
development attempt; preserve previous attempts.

Select existing cases and assemblers independently:

```bash
pixi run --locked --manifest-path environments/pixi.toml python bin/launch.py \
  --run-id selected-001 --outdir results/selected-001 --work-dir work/selected-001 \
  --cases quick-bimodal --assemblers raven-1.8.3 -- -profile local,pixi
```

`--groups read-quality` (before the `--` separator) selects the currently implemented group. Unsupported
selections fail rather than silently running a different panel. Add `-resume` to
the same launch command to reuse verified Nextflow tasks. Source code, input bytes
and the dependency lock participate in cache keys. Purging work prevents resume.

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

Copy the `references` directory to the execution host, then add `--offline` to the
Nextflow arguments and point the launcher at `--reference-dir /shared/references`.
Offline preparation rechecks the source checksum; missing or modified files stop
the workflow. Online mode runs the same preparation stage on the compute executor.
Python preparation requires Python 3.10 or later; the Pixi environment provides it.

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
simulation and scheduler waiting are excluded. RAM is sampled process-tree RSS,
which can double-count shared pages; mapper RAM is reported separately.

Inspect cleanup only after a complete, verified export:

```bash
python3 bin/cleanup.py --bundle results/quick-001/bundle --work-dir work/quick-001
```

This defaults to a dry run. Actual deletion additionally requires
`--apply --confirm-run-id quick-001`. It removes only the marked work directory,
blocks active runs, verifies retained evidence and keeps the shared reference
cache and final report. No cleanup is performed automatically.

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

The launcher automatically creates the same frozen plan. Selections belong before
the `--` separator; Nextflow options such as `-profile`, `-resume` and `--offline`
belong after it. Alternatively, pass `--plan selected-plan.json` to the launcher.
Plans bind exact version IDs, case/reference metadata, manifest/lock hashes,
resource policy and expected result slots. Typos, duplicate versions, changed
plans and unadmitted groups stop before assembly scheduling. A dedicated first
Nextflow task independently validates the plan before any reference preparation.

The [Standard proposal](docs/standard-panel-design.md) describes four candidate
whole-genome references across the five groups. Candidates are not admitted
cases, and Standard execution remains blocked until its evidence gates pass.

To prepare software before using compute nodes without network access, freeze a
plan and run `python bin/prepare-environments.py --plan selected-plan.json --out environment-preparation.json`
on the shared execution filesystem. Reference preparation remains a separate
checksummed cache step. Environment provisioning is recorded separately from
assembly/assessment time.
