Refactor the beta into a general single-isolate bacterial genome assembly benchmark covering short and long reads, with real and simulated datasets. Use the existing Nextflow repository as the implementation home. This is a direct refactor: old output formats, URL structures, historical import adapters and exact website parity are not requirements. Preserve useful scientific methods and working code where they fit the target. This handover specifies work; it does not launch the implementation agent.

# Agreed product design

Use two primary results sections: **Broad benchmarks** for performance across dataset collections, and **Targeted scenarios** for specific assembly challenges. Scenario families are plasmids, GC and composition, repeats and structure, read quality and sampling, and reproducibility. Plasmids are one family, not the organising principle for the whole product.

Read technology (short or long) and data source (real or simulated) are independent dataset properties within collections and scenarios. Show these explicitly and filter by them. Declare eligible technologies and assembler configurations for each case. Short-read workflows participate in broad benchmarks and relevant composition/reproducibility scenarios; inclusion in plasmid scenarios is explicit, not automatic. Distinguish not applicable, not run, execution failure, assessment failure and measured outcomes.

Each comparison page presents the scientific question, conditions and dataset scope, then focused plots and a compact comparison table. Individual result pages hold detailed measurements, available assembly graphs, alignments and downloads. Use consistent assembler colours, typography, spacing and metric labels. Avoid a homepage full of plots, an overall winner score, release history and version selectors. An assembler view may reuse these same current results to show performance across applicable tests.

# Catalogue and execution model

Replace overloaded track definitions with explicit collection and scenario membership, read technology, source kind, dataset identity, input recipe, assembler configuration and scientific repeat identity. A case can belong to several groups without duplicating its inputs or execution. Keep the published Wick and Holt general long-read collection scientifically distinct from targeted experiments. A broad short-read collection needs suitable paired reads and references; using the same reference genomes is possible, but the long-read collection is not automatically a short-read benchmark.

Selection must support one case, selected scenarios, multiple collections or everything eligible in one invocation. Resolve a deduplicated plan before execution. Adding an assembler reuses prepared inputs. Assembly, assessment, aggregation and rendering have separate cache dependencies. A reporting change must not invalidate assembly; an assessment repair must reuse the retained assembly. Deliberate sampling seeds, technical repeats and read-order experiments remain distinguishable scientific inputs or attempts.

# Shared preparation program

Provide one preparation program usable directly without Nextflow and callable inside Nextflow preparation processes. Resolve selected manifest dependencies, inspect the cache, construct a machine-readable work list, then either report or execute that list. Dry-run performs no downloads or software installation and shows cached, missing and invalid items, source locations, target paths and known sizes.

Connected compute nodes call the program for just their required datasets and fetch independently in parallel. For offline compute nodes, run the program for the complete selected workload on a connected transfer/submission machine, then run Nextflow against that shared cache in offline mode. The same manifests, validation and paths serve both. Nextflow does not inherently require preparation on compute nodes; executor placement is configurable, and the current PREPARE_RUN already uses the local executor.

Organise cached data by dataset and input recipe rather than scenario. Store shared references once; simulated recipes and seeds identify distinct generated reads. Use a per-item interprocess lock, recheck after acquiring it, download to a temporary path, verify expected bytes/checksums, and atomically publish. Do not let concurrent requests duplicate or corrupt the same item. Define lock support for the target shared filesystem and test it there. Offline mode never falls back to network access.

Account for references, real reads, simulator profiles, assessment resources, software environments and container images. The preparation command itself must be usable before those scientific dependencies are installed. Preflight must detect unavailable bootstrap dependencies as well as missing data. Keep scientific simulation on compute resources where appropriate; preloading downloads is not an instruction to run large simulations on a login node.

# Short read simulation and real data

Use ART for paired-end short-read simulation. Implement a recipe with a supported, pinned ART version/profile, read length, fragment-length distribution, declared coverage convention, seed and error settings. Record the exact command and realised read statistics. Validate paired identifiers, mate counts, FASTQ integrity and realised coverage. Define native replicon handling and circular-boundary behaviour explicitly; do not silently inherit an untested long-read simulation policy. Choose and verify the exact ART defaults during implementation review rather than inventing fixed values here.

Real input preparation accepts local files or downloads declared archive files with matched polished reference genomes. Validate file integrity, pairing where applicable, sample identity, reference inventory and reference provenance. A polished reference is not automatically error-free truth. Both real and simulated inputs feed the same typed assembly interface and output contract. Present their results separately within comparisons. The discussion's 400 simulated and 100 real datasets illustrated scale; they are not an agreed run budget.

# Standalone modular outputs

Produce independently understandable case results and collection/scenario summaries through one current output contract. Each package contains a readable HTML report, JSON and TSV measurements, experiment and input descriptions, assembler version/configuration, metric methods and units, statuses, provenance and available supporting artifacts. Required files are addressed by package-relative paths. No original work-directory paths or hosted-site dependency may be required to read results.

Use a small root catalogue to index current packages. Collection and scenario views reference shared case results rather than copying full assemblies into each section. Make an exported subset portable by including its referenced dependencies once. Keep the public website payload small: publish only the compact data and prepared visual assets it needs, and keep large reads, raw logs and bulky evidence outside that payload.

The web application consumes these declared directories and their catalogue; it does not discover arbitrary historical batches, invoke assemblers or calculate new sequence measurements. Share presentation components between standalone reports and the hosted site where practical. The pipeline must expose a results-only path so scientific output can succeed independently of an optional website build.

# Current results and storage policy

Maintain one current result for each case and assembler configuration, including a repeat identifier only where the scientific design requires it. Re-running replaces that result, including a newly measured failure; do not silently retain an older successful result. A newer assembler version supersedes the older version for that configuration. Record the actual version in the result, without maintaining a result history. Prevent an older version from silently displacing an already current newer version.

Replace each result atomically after its new record and available files are written and validated. Remove obsolete files owned by that result, including old success artifacts when the replacement is a failure. Leave unrelated current results intact. Technical repeats required for determinism remain part of the experiment, not operational rerun history. Do not copy shared inputs into every result. Nextflow work caches are operational storage, not website history; provide deliberate scoped cleanup without deleting unrelated shared data.

# What must change in the current implementation

| Area and current code | Required change |
| - | - |
| Scope and documentation: README, docs/benchmark-protocol-v1.md, docs/case-catalogue.md | Replace long-read-only scope and plasmid-centred assumptions with the agreed catalogue. Remove obsolete conflicting draft instructions rather than layering another design on top. |
| Planning: benchlib/planning.py and the general, real and diagnostic planning modules; assets | Establish common dataset, case, workflow and selection records. Separate source kind from benchmark membership. Replace legacy S1–S7 routing where it complicates the new taxonomy; old IDs need not be supported. |
| Orchestration: main.nf | Replace single-track branching with selection of mixed compatible collections/scenarios. Deduplicate shared inputs and executions. Preserve stage-specific caching. |
| Preparation: modules/local/preparation.nf, bin/prepare-\*.py, benchlib/references.py, real_inputs.py, general_inputs.py | Extract the common manifest resolver, cache inventory and download plan. Expose one standalone command and thin Nextflow callers. Reuse working validation, locks and atomic reference downloads. |
| Offline software: benchlib/bootstrap.py, runtime.py, nextflow\.config and container profiles | Include software and image availability in preflight. Remove unconditional online provisioning from offline operation. Resolve bootstrap requirements before scheduling. |
| Short reads: simulator and assembler adapters, modules/local/execution.nf, environments | Add ART preparation and paired-end input support. Declare supported technologies per assembler configuration. Adapt assessors to fragmented assemblies with explicitly labelled metrics. |
| Export: benchlib/report.py, bin/export-results.py, modules/local/reporting.nf | Replace the all-results export barrier with modular current results plus separate summaries. Existing export requires an empty directory and complete selected slots; replace that behaviour with scoped atomic replacement and explicit completeness records. |
| Output selection: benchlib/bootstrap.py | Replace the requirement to choose a new output directory for a changed selection. Permit adding or replacing selected current results while retaining unrelated results. |
| Reporting: reporting and website | Build the agreed navigation and common comparison layout from the new contract. Remove old batch/release-oriented presentation and historical import branches that no longer serve the product. |
| Compatibility: import-results path, historical archive adapters and website parity tests | Delete compatibility-only machinery and tests. Replace byte-for-byte old-site parity with target-contract, scientific correctness, portability and current-result replacement checks. |
| Old repository: SPREAD-Hackathon/ploptimizer assembly-benchmark | Reuse any useful scientific code, then remove the old controller as an execution dependency. Do not maintain two permanent engines. Removing compatibility requirements does not require deleting unrelated stored research data. |

# Implementation order and acceptance

1. Establish the common catalogue, current-result identities and output contract. Use small synthetic fixtures to prove selection and layout.

2. Implement shared preparation and cache inspection, including offline dependencies and concurrency.

3. Connect one existing long-read case and one ART paired-end short-read case through assembly, assessment and modular export. Exercise a matched real-read fixture through the same interface.

4. Support mixed selections, shared baselines, targeted reruns and assembler upgrades. Remove superseded branches and compatibility-only code as replacements land.

5. Rebuild the website and standalone reports around broad benchmarks and named scenario families.

6. Validate the complete small workflow on the target cluster, then document the working commands. Do not launch a full scientific panel merely to test the refactor.

Acceptance must demonstrate: dry-run lists all missing dependencies without network use; prepared offline execution succeeds with outbound access blocked; two processes requesting one item produce one verified cached copy; interrupted downloads are not accepted; corrupted cached files are rejected; selected scenarios run without unrelated tasks; an assessment/rendering change does not rerun assemblies; a copied standalone package works without original work directories; the website consumes multiple current packages without duplicating their artifacts; reruns and upgrades replace only their intended records; replacement failures remove stale success displays; real and simulated data, short and long reads, and scientific repeats remain correctly labelled. Test both successful and missing/invalid dependency paths.

# Verification already performed and remaining work

Local preparation checks passed 11 existing tests: eight reference-preparation tests and three real-read cache tests. A separate mocked-download check confirmed byte-identical offline reference reuse, reuse in online mode without another fetch, and rejection of a missing offline reference while network calls were prohibited. These tests used small fixtures, not remote scientific datasets or a cluster run.

Current source inspection also confirms standalone HTML, JSON, TSV and retained evidence export already exists; the target is to simplify and modularise it. Current Pixi environment preparation invokes install without an explicit offline control. Complete software/container preparation, shared-filesystem locking, real online transport and end-to-end offline cluster execution remain to be verified. Existing historical parity results are not acceptance requirements for the refactor.

# Source locations

[Nextflow implementation](https://github.com/happykhan/assembler-benchmark-nextflow) and [Ploptimizer assembly benchmark](https://github.com/SPREAD-Hackathon/ploptimizer/tree/main/assembly-benchmark). Code reviewed includes main.nf, nextflow\.config, modules/local/preparation.nf, modules/local/reporting.nf, benchlib/bootstrap.py, benchlib/runtime.py, benchlib/references.py, benchlib/real_inputs.py, benchlib/report.py and the protocol/catalogue/reporting documentation. Paths named as change targets beyond these are architectural targets, not claims of a complete line-by-line audit.
