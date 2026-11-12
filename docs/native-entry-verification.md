# Native Nextflow entry point

The pipeline accepts a preset directly:

```bash
nextflow run happykhan/assembler-benchmark-nextflow --preset quick
```

`PREPARE_RUN` runs on the submission host. It creates an exact frozen plan,
validates any supplied plan, refuses to replace a different output selection,
and provisions the selected locked environments serially. Reference preparation
and all scientific tasks then run under the selected executor. Preparation is
outside measured assembly/assessment time. There are no automatic assembly retries.

The default runtime is Pixi. Software resides under the downloaded pipeline's
`environments/.pixi`, and package cache writes stay there rather than in an
unmounted home directory. The reference cache defaults to the launch directory.
Both paths need sufficient writable shared storage for a cluster run.

## Container profiles

`conf/docker.config`, `conf/singularity.config` and `conf/apptainer.config`
separate runtime configuration from `local`, `slurm` and `bmrc` execution profiles,
following [nf-core's configuration conventions](https://nf-co.re/docs/running/configuration/configuration-options).
This is an independent pipeline, not an nf-core pipeline or an nf-core certification.

The common runtime is Prefix.dev Pixi 0.73.0, Linux amd64 manifest:

```
ghcr.io/prefix-dev/pixi@sha256:702f3a3c966aa63a0a57906466ec33ce9a463b532446f5584498fa429d069fd8
```

The tag's OCI index and amd64 manifest were resolved directly from GHCR on
12 November 2026. Scientific packages remain pinned by the committed Pixi lock;
they are installed on the shared pipeline filesystem and run inside the container,
rather than being baked into this runtime image. A container engine replaces
the host Pixi requirement. Initial provisioning still needs network access.
The selected image and environment-preparation receipt are retained in the bundle.

Tests target Nextflow 25.10.2, Linux x86-64, Cluster 3 Slurm and Pixi 0.73.0.
The `singularity` executable on this cluster is Apptainer 1.5.3 compatibility mode.
Docker execution cannot be tested on this cluster; its profile is provided with
that limitation. A separate `apptainer` profile is provided, but the tested
compatibility command is `-profile bmrc,singularity`.

Use `-resume` for the same selection, or a new output directory for a changed
selection. Direct Nextflow runs do not create the optional launcher's custom
cleanup ownership markers; custom cleanup therefore refuses them. Retain work
for resume and review Nextflow's own cleanup command when removing it.

## Verified Quick runs — 12 November 2026

| Runtime | Entry point | Results | Bundle checksums | Resume |
| --- | --- | --- | --- | --- |
| Pixi | GitHub repository, fresh Nextflow asset cache | 4/4 assembled and assessed | 45/45 files verified | All 13 tasks cached; no new jobs |
| Singularity | Fresh development checkout, automatic image/environment preparation | 4/4 assembled and assessed | 45/45 files verified | All 13 tasks cached; no new jobs |
| Docker | Profile configuration parsed | Not executed: Docker unavailable on Cluster 3 | — | — |

All 24 final compute-job records are terminal `COMPLETED` with exit `0:0`.
Input read SHA256s and the four sequence outcomes agree between runtimes.
Quick remains a workflow check: three outputs fall below the fixed single-alignment
completion criterion, and one meets it. Successful execution does not turn the
linear Quick fixture into a whole-genome scientific benchmark.

The fresh GitHub run tested source commit `40935752ca` with no prior plan,
reference cache or installed environments in that asset checkout. Preparation,
reference download, simulation, assembly, assessment and export all completed.
The full test suite passed **104 tests**.

Compact [verification records](../evidence/native-entry/verification.json), plans,
runtime receipts, manifests, cached traces, the verification script and terminal
scheduler accounting are committed under `evidence/native-entry`. Full bundles
remain on the cluster at the paths in the record.

The Singularity development test exposed and repaired an incompatible older Pixi
image, an unmounted home-cache location and missing cluster proxy forwarding.
The failed reference-download job remains recorded separately; it was not an
assembler failure. No assembler retry was used to obtain these Quick results.
