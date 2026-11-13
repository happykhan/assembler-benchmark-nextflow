# Common catalogue

`assets/catalogue.json` is the current declarative input to the workflow. The
schema is `schemas/catalogue-v2.schema.json`; `benchlib/catalogue.py` performs
cross-reference, eligibility and scientific-identity validation without network
access or scientific-tool installation.

## Independent properties

| Record | Purpose |
| --- | --- |
| Dataset | Biological/input identity, read technology (`short` or `long`), source kind (`real` or `simulated`), reference inventory, sample identity and file dependencies |
| Case | Dataset plus input recipe, collection/scenario memberships and scientific identity |
| Input | One dataset/recipe/seed/order combination, prepared once and reused by eligible workflows and technical repeats |
| Workflow | Stable assembler configuration ID, actual version, explicit version order, supported technologies/source kinds, pinned environment and resource requirements |
| Scientific repeat | Explicit technical/sampling/order identity when required by the experiment; not operational rerun history |
| Result slot | Case × stable workflow configuration × scientific repeat identity |

Collection/scenario memberships do not change input or result identity. Adding a
workflow does not resimulate its inputs. Changing a sampling seed or read order
changes the input recipe. Technical repeats share input bytes but have distinct
result identities. Workflow upgrades retain the configuration's stable result slot
and record their actual version; an explicit monotonic `version_order` prevents
silent downgrades. A case `science_key` guards against reusing the same case ID
for a changed scientific recipe/reference identity.

Source kind is about read origin. In particular, downloaded Wick/Holt Badread
read sets are simulated; their transport is deposited/archive download. A real
local fixture requires genuine externally supplied reads, matched read/reference
sample IDs and explicit file declarations. Being a polished reference does not
make it independently error-free truth.

## Current collections

| Collection | Contents | Execution scope |
| --- | --- | --- |
| `quick` | One 200 kb long-read simulation and one matched ART paired-end simulation | Default small workflow validation only |
| `real-validation` | Explicit local genuine ONT subset with a same-BioSample reference | Optional; supply local source paths/checksums/sample declaration |
| `reproducibility-validation` | Three declared technical executions sharing one small long-read input | Optional small reproducibility check |
| `simulated-native-genomes` | Existing five-reference, five-seed native-genome recipes and controlled input contrasts | Declared scientific collection; not automatically launched during refactor validation |
| `wick-holt-long-read` | Fifty original published long-read simulated datasets | Separate broad collection; preserve original inputs and method definition |
| `real-small-plasmids` | Admitted full deposited ONT small-plasmid-study case | Separate real-read collection; not a reproduction of unavailable historical subsets |

The five scenario IDs are `plasmids`, `gc-composition`, `repeats-structure`,
`read-quality` and `reproducibility`. Short-read workflows are included only where
explicitly eligible. A short-read plasmid case requires an explicit workflow
eligibility declaration; short-read inclusion is not automatic across all tests.

The current workflow IDs are `raven-default`, `flye-default`, `plassembler-long`,
`miniasm-raw`, `miniasm-polished` and `skesa-default`. The default Quick selection
uses Raven for long reads and SKESA for paired short reads. Cross-technology
combinations are `not_applicable`, not failed assemblies.

## Selection and inspection

```bash
nextflow run happykhan/assembler-benchmark-nextflow --collections quick --plan_only
nextflow run happykhan/assembler-benchmark-nextflow \
  --cases quick-long --workflows raven-default --plan_only
nextflow run happykhan/assembler-benchmark-nextflow \
  --collections quick,real-validation --catalogue local-catalogue.json --plan_only
python3 bin/prepare.py --collections quick --cache-dir cache --dry-run
```

Case, collection and scenario selectors combine by union and are deduplicated.
Unknown selectors fail explicitly. Unsupported combinations are listed as
`not_applicable`; they schedule no input preparation or assembler task. `--all`
resolves all eligible declared cases/configurations. Inspect it with `--plan_only`
or preparation dry-run; it is not permission or a budget for a full panel run.

For local data, use a separate catalogue file with explicit file source paths,
expected checksums and sample/reference bindings. Paths resolve relative to the
project unless absolute. Changing scientific inputs requires a corresponding new
case/scientific identity, rather than quietly overwriting a different experiment.
The shared preparation program reports missing/invalid files before computation.

## Generated reads

The native long-read recipe uses `native-error-free-v2`, exact half-up rounded
per-molecule base budgets, gamma fragment lengths and both strands. Circular
fragments can cross the origin but cannot exceed one circumference. Linear
fragments start only where the entire retained fragment fits. Bimodal mixtures
allocate bases explicitly and report both base and read proportions. Qualities
are synthetic Q40; no empirical sequencing error model is implied.

The ART recipe pins package `2016.06.05`, binary Q version `2.5.8`, HS25 paired-end
150 bp reads, fragment mean/SD 350/50 bp and seed 101 for Quick. `-f` specifies
**total sequenced-base coverage**, verified by an actual ART probe. Per-molecule
ART sampling is linear and boundary-limited, including for native circular
reference records: there is no origin wrapping or circular padding. Commands,
derived per-molecule seeds, errors, paired IDs/counts, realised read lengths and
coverage are recorded. This policy is distinct from native long-read sampling.
