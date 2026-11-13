# Shared preparation and offline execution

`bin/prepare.py` is the standalone cache command and the implementation called by
Nextflow preparation tasks. It needs Python 3.9 or newer and the Python standard
library. Scientific tools do not need to be installed to inspect a workload.

Inspect the selected workload without downloading, installing or creating cache
directories:

```bash
python3 bin/prepare.py --dry-run --cache-dir /shared/assembly-cache
```

The default selection comes from the common catalogue. The same `--cases`,
`--scenarios`, `--collections`, `--workflows` and `--all` selectors are accepted.
Use `--catalogue /path/to/catalogue.json` for a customised manifest, or use an
already resolved plan:

```bash
python3 bin/prepare.py --plan selected-plan.json \
  --cache-dir /shared/assembly-cache --dry-run --out work-list.json
python3 bin/prepare.py --work-list work-list.json --execute
```

The command re-inspects a saved work list before execution. Another process may
have admitted a missing item since the dry-run; an item may also have become
corrupt. Work lists are not permission to skip current cache validation.

## Select the execution runtime

The standalone command uses the same runtime declarations as Nextflow setup.
Pixi is the default. Select the container engine and a digest-pinned image when
preparing a container-backed run:

```bash
python3 bin/prepare.py --cases quick-long --runtime pixi \
  --container-runtime apptainer \
  --container-image ghcr.io/prefix-dev/pixi@sha256:702f3a3c966aa63a0a57906466ec33ce9a463b532446f5584498fa429d069fd8 \
  --cache-dir /shared/assembly-cache --dry-run --out container-work-list.json
python3 bin/prepare.py --work-list container-work-list.json --execute
python3 bin/prepare.py --work-list container-work-list.json --offline --dry-run
```

`--container-runtime singularity` uses a prepared SIF in the same way.
`--container-runtime docker` inventories the selected Docker daemon and explicitly
pulls only during online `--execute`. The host needs that engine available.
Advanced users can choose `--runtime native` to inspect tools already on `PATH`.
These runtime choices do not change dataset, recipe or case identities. A
selection with no eligible assembly slots does not request an image.

A saved work list already declares its runtime, so runtime flags cannot override
it. A saved common plan can be augmented with an explicit runtime before its
work list is exported. Declared manifest and lock hashes remain fixed; changing
a runtime flag never silently accepts changed source files.

## The work list

The JSON lists each declared dependency once, its kind, source URL/local path,
cache-relative target, known byte count and SHA256, inputs that require it, and
one of `cached`, `missing` or `invalid`. It also lists unavailable bootstrap
executables, including the selected software manager or container engine. An
unknown byte count stays unknown; it is not reported as a measured size. The
known-download-byte subtotal excludes cached files and unknown sizes.

Dependency kinds include reference files, real reads, simulator profiles,
assessment resources, software environments and container images. Source kind
and sequencing technology are input properties, not cache directory categories.
References shared between scenarios resolve to one target. Generated read sets
are identified separately by dataset and scientific recipe/seed in the common
plan; download preparation does not perform simulation or assembly.

Use `--inputs INPUT_ID` to prepare just the dependencies of one resolved input.
Use `--kinds reference,real_reads` to limit preparation to selected dependency
kinds. These options allow independent compute tasks to request only their own
data while sharing the same manifest and cache paths.

## Online and offline modes

On connected compute nodes, the per-input preparation task executes the required
work list and fetches missing files independently. On a connected submission or
transfer machine, `--execute` can preload the entire selected workload first.
Scientific simulation still runs in its scheduled compute task.

```bash
python3 bin/prepare.py --plan selected-plan.json \
  --cache-dir /shared/assembly-cache --execute
python3 bin/prepare.py --plan selected-plan.json \
  --cache-dir /shared/assembly-cache --offline --dry-run
```

Offline file admission never contacts a URL. Missing remote inputs stop preflight;
it does not silently retry online. Local files may be copied into the cache
without network access. Runtime inspection/provisioning uses the shared
`benchlib.runtime_v2` adapter: inspection checks existing receipts, prefixes and
images; normal offline workflow startup does not install. An explicitly requested
offline preparation operation only verifies existing software environments; it
does not run Pixi installation. Prepare missing environments online first. Missing
container images cannot be pulled offline.

## File integrity and concurrent requests

Remote files require a pinned SHA256. Known byte counts are checked as well. A
local source can omit a precomputed hash; admission records its checksum, and a
later change to that local source is detected. Scientific input validation
(FASTQ pairing, sample/reference identity and molecule inventory) remains the
typed input-preparation stage's responsibility.

Each cache target has an interprocess lock implemented with atomic directory
creation under `.locks/`. The owner records hostname, PID, Slurm ID and a unique
token. This follows the shared-filesystem lock design used after advisory `flock`
failed to exclude concurrent GPFS clients. An uncertain or killed owner's lock
is never automatically stolen. A timeout reports its owner for explicit recovery.

After acquiring a lock, the program rechecks the target. A transfer writes to a
unique temporary sibling, verifies bytes and checksum, then publishes with an
atomic hard link that cannot overwrite an existing input. Receipts are written
atomically. Failed candidates have `.partial-...` names and are never treated as
admitted files. Invalid existing inputs are reported and left unchanged.

For the published Wick/Holt collection, read dependencies can declare a bounded
TAR member range. The server must return exact `206` and `Content-Range` values;
the member header and payload hashes are checked. A server ignoring ranges is
rejected rather than downloading the complete read archive accidentally.

## Internal API

```python
work = plan_preparation(plan, cache_dir, project,
                        inspectors=runtime_inspectors,
                        offline=False, input_ids=None, kinds=None)
ready = execute_work_list(work, handlers=runtime_handlers)
```

Runtime inspectors use `(item, project, cache) -> inventory`; explicit preparation
handlers use `(item, project, cache, offline=False) -> inventory`. They return the
same `cached`/`missing`/`invalid` states. The CLI imports this integration lazily.
Unknown compute-only dependency kinds remain visible and cannot be executed by
the download command without a declared handler.

The scoped tests exercise actual local HTTP transport, two independent requesting
processes producing one download, a killed lock owner, bounded archive ranges,
interrupted/corrupt inputs, stale work lists, local inputs, offline network
prohibition and missing bootstrap dependencies. The lock must additionally be
exercised on the target cluster's actual shared filesystem before cluster
concurrency is claimed verified.

## Cluster verification — 13 November 2026

The preparation and runtime suites passed with their temporary files on the
Cluster 3 GPFS filesystem. A separate two-node Slurm probe on `compa029` and
`compa030` admitted one 77,824-byte fixture from two simultaneous requesters with
exactly **one HTTP download**. Both nodes then reused it in offline mode while
IPv4/IPv6 socket creation was blocked, with no extra download. This validates
atomic `mkdir` coordination and the post-lock cache recheck across two actual
shared-filesystem clients. The successful probe is job `35501791`; two earlier
transport-only probe attempts received HTTP 403 and admitted no cache item. The
internal test fixture now explicitly bypasses outbound HTTP proxies for its
sibling-node URL; normal dependency downloads retain their standard proxy rules.

`unshare -n` was denied on the submission host. The Linux validation helper
`tests/fixtures/network_blocker.c` instead installs an inherited seccomp filter
that denies IPv4/IPv6 `socket` calls and permits Unix-domain process IPC:

```bash
gcc -std=c11 -O2 -Wall -Wextra -Werror \
  tests/fixtures/network_blocker.c -o network-blocker
./network-blocker --probe
./network-blocker python3 bin/prepare.py --plan selected-plan.json \
  --cache-dir /shared/assembly-cache --offline --execute
```

On Cluster 3, `--probe` returned errno 97 (`EAFNOSUPPORT`) for both IP families,
and a subprocess inherited the filter. Apply this command prefix to the task
programs, including local preparation, rather than the Nextflow/Slurm controller:
the scheduler needs its own network communications. Use the wrapper for Pixi
task validation; full pipeline verification is recorded separately. `no_new_privs`
can affect setuid-based container mounting, so an
Apptainer/Singularity engine must perform its mount before the blocked task starts.

That placement was verified separately using the pinned prefix-dev/Pixi image on
13 November. `prepare_dependency` admitted the 64,069,632-byte SIF into the shared
image cache, then reused it offline while engine subprocess calls were forbidden.
Slurm job `35502501` on `compa036` ran the image's `/usr/local/bin/pixi` and reported
`pixi 0.73.0`. Running the blocker **inside** the already mounted container produced
the same version and denied both IP socket families with errno 97 while Unix
IPC remained available. Source, SIF checksum, receipt and scheduler evidence are
in `evidence/refactor-v2/container/`. This is container preparation/version
validation, not a scientific assembly run inside the image.

## Cold offline scientific preparation

A separate Quick run started with a new cache containing only verified reference
archives, software receipts and the admitted SIF. It contained no prepared
references or input read sets. All 15 Nextflow tasks completed with exit zero;
none was restored from the Nextflow task cache. Native long-read simulation and
ART paired-read simulation both executed inside Apptainer and generated fresh
inputs: 595 long reads (6,000,000 bases) and 19,995 read pairs (5,998,500 bases).
Every input receipt and recorded file checksum was verified afterwards.

The resulting two eligible Raven/SKESA slots were measured and two incompatible
slots were recorded as `not_applicable`. Every substantive task command used the
inherited network blocker; the six simulation/assembly/assessment tasks used the
pinned local SIF. The Nextflow/Slurm controller retained scheduler connectivity.
Evidence and the verification program are in `evidence/refactor-v2/offline/`.
The `final-*` proof repeats this cold-cache run against the final refactored
entry points and stable prepared-input handoff; its 15 tasks also completed with
exit zero, including both fresh simulations and both measured assembly slots.
The earlier `cold-*` proof is retained separately.
This validates the small Quick execution path, not a complete panel or a claim
that every resulting assembly reconstructs its reference completely.

## Runtime-specific inventory

Pixi and SIF inventory are filesystem-only. Pixi receipts must match the declared
manifest/lock, executable content and executable permissions, plus pinned package
metadata. Offline preparation verifies an existing environment and never installs: the
pinned Pixi 0.73.0 does not provide an `install --offline` option. Task execution uses
`pixi run --locked --no-install` after preflight, with network access independently
blocked during offline validation. Sources changing during online installation do
not produce an accepted receipt.

Docker inventory uses the read-only `docker image inspect` command against the
active local daemon. It verifies the exact repository digest and image ID; it
never pulls during inventory. Explicit online preparation can pull the pinned
digest and write a receipt. Offline preparation requires that image already be
available in the execution daemon and never pulls. Copying a shared receipt does
not transfer an image between Docker daemons. Docker receipts are JSON metadata,
not SIF files.

Advanced `native` software mode inspects the required executable paths and hashes
without installation or version commands. Exact scientific tool versions are
checked at invocation. A missing native executable stops preparation rather than
silently switching to a software installer.
