# Single-isolate genome assembly benchmarks

One Nextflow workflow for **bacterial isolate assembly with short and long reads,
using real and simulated datasets**. The product has two results sections:
**Broad benchmarks** for dataset collections and **Targeted scenarios** for
plasmids, GC/composition, repeats/structure, read quality/sampling and
reproducibility. Hybrid and metagenomic workflows are outside the scope.

The current refactor uses a common catalogue and modular current-result packages.
Old batch formats, historical import adapters and website URL parity are not the
execution interface. Existing stored research data are not deleted by the refactor.

## Start small

On a Linux machine with Nextflow, its Java runtime, Pixi and a host Python 3.9+
interpreter available:

```bash
nextflow run happykhan/assembler-benchmark-nextflow \
  --collections quick --cache_dir cache --outdir current -profile local,pixi
```

Quick selects a matched 200 kb reference fixture: one error-free native long-read
input assembled with Raven, and one ART paired-end short-read input assembled
with SKESA. This is **two eligible assembly slots**, plus two explicit
cross-technology `not_applicable` entries. It checks the workflow, not scientific
performance across whole genomes. Input and software preparation happen through
Nextflow; no preliminary Python preparation command is required.

For Cluster 3, change the execution profile to `-profile bmrc,pixi`. The scientific
processes run on compute nodes. `SETUP` prepares software on the submission host;
`ADMIT_INPUT` admits downloads for each required input. Add `transfer_host` when
downloads must also run on the connected submission host. Simulation remains a
compute task.

Python is needed on the submission host before the scientific environments are
prepared. If the default `python3` is older than 3.9, pass an existing compatible
interpreter explicitly, for example `--bootstrap_python /path/to/python3.11`.
Use the actual path available on your host; the workflow does not install this
bootstrap interpreter. Scientific tasks use their pinned environments.

The pins target Linux. Container profiles `docker`, `singularity` and `apptainer`
are alternatives to Pixi, with their own runtime/image availability requirements.
Use `native_tools` only when the declared tools have already been prepared.

**Validation status:** small Quick and matched real-input paths have completed on
Cluster 3. Cold offline Quick passed all 15 tasks with task-program network access
blocked, including native long-read and ART paired-end simulation, assembly,
assessment, packages and website rendering. Cache reuse and portable desktop/mobile
reports are verified. The final narrow mixed selection has seven measured results
and eleven inapplicable combinations across three prepared inputs, including real
reads and three technical repeats. No full panel or production deployment is claimed. See the [acceptance matrix and evidence](docs/refactor-verification.md).

## Choose the scientific workload

`--preset quick` is a convenience alias for `--collections quick`.
`--preset standard` selects `simulated-native-genomes`; it can be a large
scientific workload, so inspect it with `--plan_only` first. Preset collections
combine with explicitly selected cases, collections and scenarios by union.

```bash
# Inspect everything declared; no download, installation or scientific execution.
nextflow run happykhan/assembler-benchmark-nextflow --all --plan_only -profile native_tools

# Select one case and one compatible workflow.
nextflow run happykhan/assembler-benchmark-nextflow \
  --cases quick-long --workflows raven-default --outdir current -profile bmrc,pixi

# Select several collections; overlapping cases and inputs are deduplicated.
nextflow run happykhan/assembler-benchmark-nextflow \
  --collections quick,real-validation --catalogue local-catalogue.json \
  --cache_dir cache --outdir current -profile bmrc,pixi
```

`--cases`, `--collections` and `--scenarios` combine by **union**. `--workflows`
selects stable assembler configurations. Read technology and source kind are
independent properties, not competing tracks. An ineligible workflow is shown as
`not_applicable` and is not scheduled. `--all` resolves all declared eligible
cases/configurations; it is not a smoke-test budget. Do not use it to validate a
refactor by launching a full panel.

The optional real-validation case requires a genuine externally supplied ONT
subset and its matched sample/reference declaration in a local catalogue. Missing
local files are reported; simulated data are never substituted and labelled real.
The Wick/Holt collection remains separate: its deposited Badread simulations are
**simulated data**, even though preparation downloads their published bytes.

See [the catalogue](docs/case-catalogue.md) and
[scientific methods and scope](docs/benchmark-protocol-v1.md).

## Prepare online, execute offline

The same preparation program is usable without Nextflow. It requires Python 3.9+
as a bootstrap interpreter, but it does not require scientific tools to inspect
the workload. Pixi or a container runtime is needed only for the selected runtime
preparation. Dry-run is the default:

```bash
python3 bin/prepare.py --collections quick --cache-dir /shared/benchmark-cache --dry-run
python3 bin/prepare.py --collections quick --cache-dir /shared/benchmark-cache --execute
```

The work list reports cached, missing and invalid items, their sources, target
paths and known sizes. It covers references, read files, simulator/assessment
resources, environments and container images. Preloading never starts scientific
simulation. Two requests for one dependency use one lock and one verified atomic
publication. Invalid cached bytes are rejected, not silently reused or replaced.

After preparation on a connected machine, use the same shared cache:

```bash
nextflow run happykhan/assembler-benchmark-nextflow --collections quick \
  --cache_dir /shared/benchmark-cache --outdir current --offline \
  -profile bmrc,pixi
```

Offline mode never falls back to a network fetch. Missing or incompatible data,
bootstrap tools, software or images must be resolved before scientific execution.
`--prepare_only` runs dependency preparation without simulations or assemblies;
`--plan_only` performs no downloads or installations.

## Current results, portable reports and the website

Each case/configuration publishes independently. A completed case does not wait
for unrelated cases to finish. Its package contains HTML, JSON and TSV metrics,
input/experiment descriptions, actual software version and available supporting
artifacts. A small root `catalogue.json` indexes current packages. Shared
references and other dependencies are stored once, and subset export includes
referenced dependencies once.

A rerun replaces the selected current result, including a newly measured failure;
old success artifacts are removed. Unrelated results are retained. Newer workflow
versions replace older ones for the same stable configuration, while an older
version cannot silently displace a newer current result. Scientific technical
repeats have explicit identities and remain separate experimental results.

```bash
# Deliberate selected rerun into the same current-results directory.
nextflow run happykhan/assembler-benchmark-nextflow --cases quick-long \
  --workflows raven-default --rerun --outdir current -profile bmrc,pixi

# Retained scientific packages can succeed without a hosted-site build.
nextflow run happykhan/assembler-benchmark-nextflow --collections quick \
  --results_only --outdir current -profile bmrc,pixi

# Render existing current results without preparing inputs or running science.
nextflow run happykhan/assembler-benchmark-nextflow --render_only --outdir current
```

Assembly, assessment, publication, aggregation and rendering have separate cache
dependencies. `-resume` reuses successful computation; an assessment or rendering
repair must not rerun assemblies. The web application reads declared current
packages, not arbitrary work directories. It never invokes assemblers or computes
new sequence measurements. Large reads, raw logs and bulky evidence stay outside
the compact website payload.

## Development

The common implementation is in `benchlib/catalogue.py`, `preparation.py`,
`inputs_v2.py`, `assembly.py`, `measurement.py` and `current_results.py`, connected by `main.nf`
and `modules/local/`. The current reporting implementation consumes the same
contract. `assets/catalogue.json` declares datasets, input recipes, stable
workflow configurations, collections, scenario memberships and dependencies.

```bash
python3 -m unittest discover -s tests -v
```

The acceptance criteria are in [the refactor specification](docs/refactor-specification.md).
Use tiny fixtures and representative target-cluster runs. Do not launch a full
scientific panel merely to test orchestration. Cleanup must be deliberate and
scoped to owned operational storage; current packages and unrelated shared inputs
are not disposable Nextflow history.

## Deliberate work cleanup

Use a separate `-w work/quick-validation` root for a narrow owned cleanup scope.
Nextflow records its lifecycle; nonempty unowned/legacy work is preserved and is
not adopted. After the controller exits, inspect first:

```bash
python3 bin/cleanup.py --work-dir work/quick-validation
# Only after reviewing that dry-run scope:
python3 bin/cleanup.py --work-dir work/quick-validation --execute
```

Shared inputs/software and current packages are protected. Active, failed,
unowned or overlapping roots are refused. Cleanup disables task resume; it does
not remove the scientific cache or unrelated results. See [cleanup](docs/cleanup.md).
