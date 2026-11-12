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
