# Benchmark protocol v1

**Review draft, revised 12 November 2026. Full protocol not yet approved, frozen or executable.**

Review decisions recorded: include a fifth, below-30% GC reference; use five
sampling seeds; defer the reserved error/bias scenarios; replace the old
execution/report-production pipeline fully with Nextflow, with selectable
benchmarks and scenarios. The remaining design
choices still require review. These decisions do not authorise execution.

This document proposes the scientific design for the Nextflow benchmark. It does
not authorise downloads, simulation, assembly or deployment. Existing executable
manifests retain their current behaviour while this draft is reviewed. Once
agreed, a versioned suite manifest must implement the protocol and pass its
admission gates before any scientific release starts.

## 1. Scope and scientific questions

The benchmark covers single-isolate bacterial long-read assembly. It excludes
hybrid assembly and metagenomic samples. An assembler plus any polishing stages
is one declared workflow configuration. Short-read information used by a source
study to construct its reference is recorded as provenance and never supplied to
our tested workflows.

The five scenario groups remain plasmids, GC/composition, repeats/structure,
read quality/sampling, and reproducibility. Each scenario declares a comparison,
its controls, eligible inputs and intended interpretation. Simulated and real
results are reported in separate sections. Quick checks execution; Standard
contains the curated scientific cases.

The first release should establish which declared workflows recover the native
chromosome and plasmids under controlled conditions, how outcomes change across
specified challenges, and how stable outputs are when inputs or executions are
repeated. It should report resource use alongside scientific measurements.
There is no overall winner score.


### One pipeline and a full replacement contract

Nextflow will be the sole execution pipeline. It must replace all existing
long-read benchmark functionality, including the general Wick/Holt collection,
the existing website scenarios and their evidence/reporting capabilities. The
new repository is currently a partial implementation of that target. Maintaining
two permanent execution systems is not the design.

Users select benchmark collections, scenario groups and individual cases through
one entry point. The general published-data collection and the targeted scenarios
share preparation, execution, assessment, retention and export modules. They keep
separate scientific definitions and denominators. Selection resolves to a frozen
case/run plan before scheduling; shared inputs and runs are deduplicated.

The existing `--groups` and `--cases` selectors are the starting point. The final
selector syntax and general-collection catalogue still need implementation/review;
this draft does not advertise a working general-data selector today. Quick and
Standard remain run-size/scientific-panel presets rather than separate engines.

The intended delivery path is:

```text
One Nextflow entry point
  select general published datasets and/or selected scenario groups/cases
  prepare or admit inputs, execute workflows, assess and verify
  export the complete versioned results/evidence bundle
Website renderer
  consume that bundle to build pages, figures, graph views and downloads
```

Nextflow must produce every scientific measurement and retained evidence item
needed by selected website scenarios. The renderer may format data and draw
figures from supplied measurements/coordinates; it must not run assemblies,
perform new sequence assessments or rediscover source batches. One bundle
contract must cover general and scenario results with explicit method/cohort
labels. The current new-pipeline standalone bundle has not yet been connected
to the existing website renderer.

Internal Python functions are allowed behind Nextflow processes. Users must not
operate a separate Python/Slurm controller or run Python preparation scripts
before the normal Nextflow command. A standalone website build must also work
from a sealed bundle, without operating the retired pipeline. Deployment is a
separately authorised publication step, not an automatic effect of running cases.

Full replacement requires a versioned capability checklist:

| Existing capability | Required Nextflow-based replacement |
| --- | --- |
| General Wick/Holt published-data benchmark | Admit the exact selected published read/reference bytes, retain archive/member bindings, and use the separate longest-alignment endpoint; support import of existing frozen results and explicitly selected new executions |
| S1 ordinary recovery and S2 relative plasmid coverage | Selectable native chromosome/plasmid cases and matched coverage contrasts; retain original and revised historical cohort labels |
| S3 repeated execution and S7 read-order sensitivity | Explicit repeat/order/thread/configuration identities; preserve output-agreement measures separately from reference recovery and retain historical run counts |
| S4 small-plasmid/read-length cases | Selectable small-plasmid cases, matched input recipes and per-molecule outcomes; preserve original methods alongside newly versioned methods |
| S5 native linear molecules | Native linear as well as circular topology throughout preparation, assessment and reporting; preserve published S5 evidence |
| S6 read-error cases | Preserve and render historical continuous measurements and unscored fields; new error experiments remain deferred under the current v1 decision |
| Existing workflow definitions and intermediate phases | Port the in-scope workflow/configuration roster, including Plassembler's final plasmids plus retained chromosome and the Miniasm/Minipolish raw phase; missing adapters remain explicit parity gaps |
| Assessment and failure accounting | Preserve exact-copy, longest-alignment, paper-rule and agreement definitions as separate versioned methods; retain failures, attempts, hashes and unresolved measurements |
| Graphs, reviewed alignments and reports | Retain available graph/origin evidence, saved alignment coordinates, detailed result reports, source tables and figures; missing evidence stays missing |
| Website and downloadable outputs | Match the existing general, scenario, aggregate, methods and individual-result surfaces, graph inspection and downloads from the common bundle |
| Operation and retention | Online/offline preparation, locked software, scheduler/resource accounting, resume, release verification and a separately reviewed cleanup/restoration contract |

This checklist is broader than the new scientific scenario matrix. New scenarios
extend the same engine. They do not justify dropping existing linear-molecule,
graph, comparison or reporting functionality.

Retain the published 200 general outcomes and historical S1–S7 evidence as frozen
records, with original identifiers, scores, methods, attempts and hashes. Import
and schema adaptation must be lossless; migration does not require reassembly.
Old and new measurements are pooled only when an explicit scientific contract
permits it. Existing published output remains available during migration, but the
old execution controller is retired at cutover rather than retained as a fallback.

Cutover requires a reviewed source-capability inventory, representative execution
checks, lossless import checks for historical records, and website/data parity
checks. Existing S5/S7 views and the 200-outcome general report must remain
verifiable. The replacement must build and render without invoking the old
controller. No migration, retirement, rerun or deployment is authorised by this
draft revision.

## 2. Status of work already done

| Existing work | Status under this protocol |
| --- | --- |
| Quick, two 200 kb fixture conditions | Engineering checks, excluded from scientific summaries |
| Two whole-chromosome simulated baselines, seed 42 | Development observations, excluded from the proposed new simulation panel |
| ATCC25922 full-read real-data pilot | Previously observed development case; retain and disclose its inclusion in any real-data release |
| General benchmark and S1–S7 in `ploptimizer/assembly-benchmark` | Frozen historical records to preserve/import during full Nextflow replacement; scientific cohorts/methods stay distinct and are not automatically pooled |

The pilots informed this draft. This is not retrospective preregistration of
those results. New simulated inputs use the proposed fixed seeds 101, 202,
303, 404 and 505, implementing the agreed five sampling seeds. These are workload choices, not selected for favourable recovery.

A matching real pilot execution may be reused if its input, configuration and
resource contract exactly match the approved suite. It remains visibly marked
as observed before protocol approval. A reporting repair can reassess a retained
assembly without generating another assembly attempt.

## 3. Units, identifiers and shared artefacts

| Object | Definition and required identity |
| --- | --- |
| Suite release | Protocol version, selected scenarios, admitted case IDs, workflow versions, assessor versions and expected run slots |
| Scenario | Scientific question, baseline/challenge links, controls and interpretation limits |
| Case | Reference/dataset plus a declared condition; may belong to several scenario groups |
| Input set | Exact read bytes and provenance; reference inventory; generator or source policy; sampling seed and order transform where relevant |
| Workflow configuration | Assembler/version, polishing stages if present, explicit command, locked environment, threads and resource limits |
| Run attempt | Input-set ID × workflow configuration × execution-replicate index; linked to preserved scheduler and execution records |
| Assessment | Retained assembly hash × versioned assessor and parameters; may be repeated independently of assembly |

A case links to inputs and its comparator. A group membership does not create
another input set or another execution. The same WCFS1 baseline, for example,
contributes to composition and plasmid summaries without being run twice.

Replicons are nested within isolates. Simulation seeds represent read-sampling
variation. Execution repeats and read-order changes represent different technical
axes. None adds independent biological isolates.

The implementation must support these distinctions before expansion. In
particular, replace the assumption that a case has only one `group` with explicit
scenario memberships, and keep biological, sampling, order and execution IDs
separate. The protocol JSON will be a non-executable design object until admitted.

## 4. Proposed input panels

### Simulated foundation

Retain whole native genomes and their declared replicon complements.

| Reference | Role | Current admission state |
| --- | --- | --- |
| *Bacillus subtilis* 168, NC_000964.3 | Shared middle-composition baseline; sampling, repeat-span and reproducibility contrasts | Whole chromosome admitted for development |
| *Lactococcus lactis* IL1403, AE005176.1 | Lower-composition chromosome | Whole chromosome admitted for development |
| *Mesoplasma florum* L1, AE017263.1; RefSeq alias candidate NC_006055.1 | Fifth reference, nominated for the agreed below-30% GC slot; published genome 793,224 bp and about 27.0% GC | Candidate only; exact source/alias, complete inventory, payload hashes and recomputed GC admission pending |
| *Micrococcus luteus* NCTC 2665, CP001628.1 candidate | High-composition chromosome | Exact source/alias and payload admission pending |
| *Lactiplantibacillus plantarum* WCFS1, AL935263.2 plus native pWCFS101/102/103 | Native small/medium plasmids and composition baseline | Compatible source inventory, plasmid accession versions and payload admission pending |

Source details and candidate accession evidence are in the existing
[panel proposal](standard-panel-design.md). Admission must recompute sequence
statistics from exact source bytes. Species labels and approximate published GC
values do not replace those measurements.

The five-reference foundation now includes a below-30% GC slot. The nominated
candidate, *Mesoplasma florum* L1, is reported as 793,224 bp and 27.0% GC in
[the primary study's Table 1](https://journals.asm.org/doi/10.1128/msystems.00198-17).
The [NCBI accession record](https://www.ncbi.nlm.nih.gov/nuccore/NC_006055.1)
identifies the versioned RefSeq candidate. Confirm its identity with AE017263.1
and recompute all statistics during later admission. No genome payload has been
downloaded for this protocol revision. The low-GC slot is agreed; the candidate
nomination and exact archival binding remain review/admission items.

The proposed composition range is approximately 27–73% GC, subject to those
checks. This is a small descriptive panel across species. Genome size, repeats
and replicon complement are confounded with composition; the small L1 genome
makes that size difference particularly relevant. The panel cannot establish a
causal GC effect or generalise from one low-GC genome to all low-GC organisms.

### Real-data companion

Propose the 12 annotation-consistent isolates in the frozen Johnson et al.
metadata inventory. Their declared inventory contains 31 plasmids, including
nine below 10 kb. These are metadata counts, subject to payload admission.

The proposed IDs are 2020QW-00078, 2021QW-00045, 2021QW-00056, 2021QW-00057,
2022QW-00133, ATCC14028, ATCC14458, ATCC23235, ATCC25922, ATCC25923, ATCC33090
and ATCCBAA2146. Each case requires the exact ONT run and same-BioSample reference
inventory in the [study manifest](../assets/real-data/small-plasmids-paper.json).
Only ATCC25922 has completed byte admission and an end-to-end pilot.

The two NG cases remain excluded because archive chromosome/plasmid labels
conflict with the proposed biological roles. They require an evidenced resolution
and a documented protocol amendment. Recovery results are not an exclusion rule.

Use full deposited ONT read sets, with no filtering or subsampling in this
release. Current versions and these full-read inputs constitute a new comparison
using the study's data. Original historical subset IDs are unavailable. Reference
construction partly used tested assembler families and other sequencing evidence;
reference agreement is therefore a comparator with documented limitations.
The cohort's chemistry is also too narrow to represent all contemporary ONT data.

## 5. Simulation contract

Baseline settings are 30× per replicon, error-free reads, and requested fragment
length mean/SD 10,000/2,000 bp. Use seeds 101, 202, 303, 404 and 505 for
independent sampling blocks. Five sampling seeds do not mean five execution
repeats: three executions per order and one reproducibility anchor per track
remain proposed, as budgeted below. The present simulator is Badread 0.4.2; its length parameters describe a
gamma distribution. Actual read lengths and realised coverage must be measured,
not inferred from requested parameters. [Badread's versioned documentation](https://raw.githubusercontent.com/rrwick/Badread/v0.4.2/README.md)
describes its length and circular-reference behaviour.

Adapters, junk, random sequence, chimeras and glitches are disabled in the
error-free foundation. Their effects require separate admitted conditions.
Every read must be verifiable against its source coordinates, strand and declared
circular wrap behaviour.

Proposed physical-length rule: cap a sampled fragment at its source molecule's
native length, allow a circular read to cross the reference origin, and prohibit
multiple circuits through the molecule. A 10 kb request must not silently create
five tandem copies of a 1.9 kb plasmid. This changes the realised small-plasmid
length distribution and must be reported. Any concatemer scenario would require
its own case. The current generator does not yet satisfy this multi-replicon
contract; it must be implemented and validated before those cases are admitted.

Define base budgets per replicon. Use round-half-up integer budgets where a
requested depth produces a fractional base count. A final read may be shortened
to meet the exact budget; record that operation and verify retained coordinates.
Do not use a simulator's small-plasmid dropout option in the intrinsic recovery
baseline. Confirm realised budgets independently instead of relying on relative
sampling weights.

Comparisons share reference and planned seed blocks. That does not imply that
all read starts are identical between different length recipes. Use distinct,
recorded random streams for sampling, length modes and interleaving. The 10×
coverage case should be a deterministic base-budget prefix of its 30× baseline,
with any terminal trimming recorded.

## 6. Scenario matrix

Each row below counts only new input sets or extra executions. Comparator inputs
are reused. A recipe is a scientific condition, not a new assembler setting.

| ID / group | Scientific comparison | Fixed controls | New inputs / attempts per workflow version | Admission gate and interpretation |
| --- | --- | --- | ---: | --- |
| B / composition | Whole-genome baseline across five references | Error-free; 30× per replicon; 10 kb/2 kb length parameters; five sampling seeds | 25 simulated inputs; 25 attempts | All five source inventories must be admitted; descriptive composition strata, no causal GC claim |
| Q1 / sampling | 10× against the B. subtilis 30× baseline | Same reference and baseline-derived read order/quality | 5 derived lower-depth inputs; 5 attempts | Exact nested base budgets and actual coverage verified |
| Q2 / sampling | Shorter reads, mean/SD 2,000/400 bp, against the 10 kb baseline | B. subtilis; 30× total bases; error-free | 5 simulated inputs; 5 attempts | Realised distribution measured; read count may change |
| Q3 / sampling | Bimodal reads against the single long mode | B. subtilis; 30× total bases; error-free; 50% bases from 1,000/250 bp mode and 50% from 10,000/2,000 bp mode | 5 simulated inputs; 5 attempts | Freeze interleaving; report base fractions and read-count fractions separately |
| P1/P2 / plasmids | Plasmid:chromosome depth ratios 0.25 and 4 against the WCFS1 ratio-1 baseline | Chromosome 30×; same native inventory, per-replicon length policy and error-free model | 10 simulated inputs; 10 attempts | Plasmids receive 7.5× or 120×; total isolate bases change deliberately; no fixed-whole-isolate-base claim |
| T / repeats | Longer reads, mean/SD 20,000/4,000 bp, compared with B and Q2 | B. subtilis; same 30× base budget and error-free model | 5 simulated inputs; 5 attempts | Freeze a repeat inventory, measure actual bridging, validate structural assessment; length alone is not proof of a repeat effect |
| R / real plasmids | Recovery across the 12 fixed study isolates, stratified by plasmid size | Same admitted full-read file for every workflow/version within an isolate | 12 real input sets; 12 attempts | Same-sample references and complete native inventories; descriptive size association, not an isolated causal size effect |
| X-S / reproducibility | Original bytes versus two deterministic read orders; three executions of each | One B. subtilis seed-101 baseline; same host class, threads and configuration | 2 order derivatives; 8 extra attempts | Baseline execution supplies the first original-order repeat; byte and sequence equivalence reported separately |
| X-R / reproducibility | Same design on the real ATCC25922 input | Original full-read multiset, including qualities and headers | 2 order derivatives; 8 extra attempts | Technical stability on one real input; no general claim about all datasets |

The two order derivatives are a deterministic hash permutation and a stable
length-ascending order. Define the hash algorithm, transform seed and tie-breaker
before generating them. Reordering preserves complete FASTQ records, sequences,
qualities, identifiers and multiplicities. Preserve the original archive order
as the comparator. Identical-input execution repeats do not download, simulate
or reorder reads again.

The repeat inventory's algorithm/thresholds and the structural assessor remain
review/admission items. Until validated, row T is blocked and no repeat-resolution
or structural-correctness conclusion can enter a completed v1 release.

### Agreed deferral: error and bias conditions outside v1

Controlled sequencing errors, uneven within-replicon coverage, chimeras and
composition-associated sequencing bias are deferred from v1 by the current
review decision. They remain possible later extensions. Each needs an
exact generator recipe, verification of the realised perturbation, and a matched
comparator before admission. The earlier proposal's undefined error arm does not
count as a ready condition. Additions require a protocol amendment and revised
budget; they cannot be activated by changing a label.

## 7. Run budget

An attempt is one scientific workflow execution. It excludes downloads, input
preparation, read-support mapping, assessment and export tasks. This table is a
budget for the newly designed scenario suite after approval and admission, not
permission to run. It is not a budget for the entire functionality migration.

| Component | Attempts per workflow version | Two current versions |
| --- | ---: | ---: |
| Five simulated baselines × five sampling seeds | 25 | 50 |
| Three sampling contrasts × five sampling seeds | 15 | 30 |
| Two plasmid-depth contrasts × five sampling seeds | 10 | 20 |
| One extra long-read repeat-span contrast × five sampling seeds | 5 | 10 |
| Extra simulated-input reproducibility executions | 8 | 16 |
| Simulated subtotal | **63** | **126** |
| Twelve real full-read cases | 12 | 24 |
| Extra real-input reproducibility executions | 8 | 16 |
| Real subtotal | **20** | **40** |
| **Total** | **83** | **166** |

There are 55 distinct simulated input sets before read-order derivatives,
12 original real input sets, and four read-order derivatives: **71 distinct
prepared read sets**. Of the 55 simulated sets, Q1's five are derived prefixes;
50 require independent simulation recipes/seed instances. All 71 have individual
byte identities. Across two workflow versions there are 142 distinct input/version
pairs, plus 24 extra identical-input execution repeats, giving 166 attempts.

The reproducibility calculation is nine executions per anchor/version: three
orders × three repeats. One original-order execution is already in the baseline
or real cohort. Each anchor therefore adds eight, not nine, attempts. There are
two anchors. All workflows receive the same prepared inputs and transforms.

The initial two version definitions are Flye 2.9.6 and Raven 1.8.3. The pilot's
two matching real executions may be reused after review, yielding at most
164 newly scheduled assemblies for this design. Reuse requires exact provenance
and explicit disclosure. This draft does not claim that the rest of the suite
has been admitted or run.

With five sampling seeds, the previous four-reference design would require
156 attempts across the two workflows. The fifth reference adds five baseline
inputs per workflow, making **166**, rather than adding the old three-seed
six-attempt increment. Deferred error/bias scenarios contribute zero attempts.
One newly admitted assembler/version adds **83 attempts** against the same
71 prepared read sets, without resimulation.

| Future amendment, outside the agreed v1 scope | Additional attempts | Revised total if selected alone |
| --- | ---: | ---: |
| Sixth composition reference, five baseline seeds, two workflow versions | 10 | 176 |
| One later admitted error condition, five seeds, two workflow versions | 10 | 176 |
| One additional workflow configuration/version over the current panel | 83 | 249 |

These are amendment costs, not current execution choices. Reproducibility anchors
remain one specified sampling block per track, not one anchor per sampling seed.

### General benchmark and migration budget boundary

The 166 attempts above cover the proposed new scenario matrix only. Lossless
import of the existing 200 general outcomes and historical scenario evidence
requires **zero new assembly attempts**. Import/render verification costs are
separate from scientific execution counts.

A fresh run of the frozen 50-dataset general collection costs `50 × M` assembly
attempts for `M` selected workflow configurations. Matching the four-workflow
historical roster would therefore add 200 attempts; selecting two would add 100.
Those configurations still need explicit adapter/version admission in Nextflow.
Neither rerun is approved or included in the 166. Any new executions of historical
S1–S7 cases likewise need an explicit frozen selection and separate budget.

Historical import, new scenario execution and a general-dataset rerun are
selectable operations with separate provenance. They must not trigger one another
implicitly. Full feature parity and the scientific run budget are separate gates.

## 8. Workflow configurations and resources

Freeze immutable workflow IDs and commands before the full panel. The currently
implemented Flye configuration uses `--nano-raw`; its v1 inclusion is a review
choice, not a claim that it is optimal for every chemistry. A high-quality-read
mode would be a separately declared configuration, not a post-result replacement.
A whole extra configuration costs the same 83 attempts as an added version.

Propose four CPUs, 16 GB RAM and four hours per assembly attempt, with no automatic
retry of software crashes, timeouts or out-of-memory outcomes. These ceilings
are experimental conditions, not expected consumption. The 166-attempt assembly
ceiling is 664 aggregate task-hours or 2,656 allocated CPU-hours. Preparation and
assessment allocations are additional; this is not an elapsed-time forecast.
Keep scheduler capacity at 1,000 rather than imposing an unrelated lower cap.

Provision software serially before releasing assembly work. Record scheduler
waiting, downloads and input preparation separately. Report assembler
verification/execution time and assessment time separately as well as their
sum. Keep input-support diagnostic time separate. Process-tree RSS sampling and
scheduler peak RAM are identified by method; do not silently substitute one.

Fix hardware class and threads for repeated-execution comparisons. Runtime/host
portability checks form separate engineering runs, not extra scientific
replicates. Adding a polisher or changing an input mode creates a new workflow
configuration and preserves the old result.

## 9. Assessments and reporting rules

The primary sequence endpoint remains `wick-longest-alignment-v1`: longest
single alignment against a tripled reference divided by native molecule length,
completion at ≥99%, uncapped contiguity, and identity/indels only where measured.
Chromosomes and plasmids remain separate. [Wick and Holt's repository](https://github.com/rrwick/Long-read-assembler-comparison)
documents the reference-triplication and contiguity approach.

The separate `johnson-2023-summed-block-rule-v1` is a historical comparator for
real plasmids. It uses strict >90% summed alignment blocks, a fragmented fallback,
a multiple-recovering-contig flag and a length-based chromosome-incorporation
heuristic. It can count overlapping contributions. It is never merged into the
primary verdict or treated as deduplicated sequence breadth. See
[Johnson et al.](https://pmc.ncbi.nlm.nih.gov/articles/PMC10272865/) and the
[pilot method audit](real-small-plasmid-pilot.md).

Independent read-support mapping is diagnostic evidence. Coverage and mapped-read
counts do not establish correct assembly or unbiased copy number. Reference
breadth across all assembly contigs is also distinct from single-alignment
completion and must be labelled separately if reported.

Structural correctness, missing/extra sequence, within-contig duplication and
circular-junction correctness need separately versioned validated assessors.
The existing paper duplication/incorporation heuristics do not supply those
assessments. Unimplemented fields remain unmeasured. The proposed repeat/structure
release gate requires this work, rather than interpreting N50 or 99% contiguity
as proof of correctness.

For reproducibility, report exact byte identity, canonical sequence/multiset
agreement, and variation in reference-based metrics separately. Canonicalisation
must define contig order, strand and circular rotation treatment and must not
normalise away biological discrepancies. Failure of one comparison does not
silently replace another's verdict.

## 10. Denominators, aggregation and failures

Report workflow completion and conditional molecular recovery together. Workflow
completion uses all planned attempts as its denominator and requires a completed
assembly plus valid required assessments. A below-threshold molecular outcome
can still be a successfully completed benchmark execution.

Conditional recovery is the number of molecules meeting the named criterion
divided by the number with a valid measurement. Always show the excluded counts
and reasons beside it, so conditional recovery cannot hide execution failures.
An optional end-to-end recovery yield uses all planned molecule slots only once
orchestration and measurement errors have been resolved. A workflow failure means
no recovery delivered by that workflow, not biological sequence absence.

| State | Accounting and permitted interpretation |
| --- | --- |
| Completed assembly, valid assessment, criterion met/below threshold | Recorded sequence outcome under that named method |
| Software crash, timeout or out-of-memory under the frozen resource limit | Recorded execution outcome; no sequence verdict; retained attempt, no outcome-driven rerun |
| Input/download/orchestration error | Unresolved execution infrastructure; repair only with evidence and preserved attempts |
| Assessment error | Unresolved measurement; preserve the assembly; reassess after generic repair without reassembling |
| Pending or missing record | Unresolved slot; never labelled running without scheduler evidence or counted as absence |

No scientific release is complete while planned input admission, orchestration,
bindings or required measurement errors remain unresolved. Completed software
or fixed-resource failures can be accounted outcomes, with explicit failure
counts. Never quietly reduce the panel denominator to publish a partial release.

Show each condition and isolate first. For composition, show individual genomes
rather than a pooled causal GC estimate. For real plasmids, use predeclared size
bins <10 kb, 10–<100 kb and ≥100 kb; display both per-isolate fractions and pooled
molecule counts. An optional macro-average gives each isolate equal weight and
states how zero-eligible-molecule strata are handled. Plasmids, seeds, read orders
and technical repeats must not inflate biological sample size.

Use reference/seed blocks for simulated contrasts and isolate blocks for real
comparisons. Five sampling seeds and two reproducibility anchors support descriptive
variation, not reliable general inferential claims. Do not present ordinary
binomial intervals treating correlated plasmids or repeated executions as
independent. Any later uncertainty model must state its resampling unit and
small-sample limitations before results are summarised.

## 11. Admission, execution and release gates

After protocol review, freeze exact case and comparator IDs, memberships, seeds,
transform definitions, payload hashes, workflow definitions, assessor versions,
resource limits and all 166 expected slots. Record remaining blockers. Admission
failure does not license a substitute chosen after viewing assembly results.

Before starting Standard, implement and validate native multi-replicon simulation,
per-replicon budgets, the circular length cap, read-order transforms, repeat
inventory and required structural assessors. Exercise these through small
engineering cases. The full matrix remains blocked until these gates pass or
an explicit protocol amendment reduces scope and budget.

Execute the simulated panel first. Admit the real companion independently using
same-sample reference checks, source byte validation and reference-confidence
records. The two tracks may have separate complete release statuses; they are
not pooled into a single performance estimate.

Each results bundle retains input/source provenance, original attempts,
assemblies/available graphs, alignments, method versions, measured values,
failure states, resource scope, TSV/JSON, standalone HTML and checksums. The common bundle must supply all required website scenario and general-benchmark
evidence. Website publication is a separate consumer step. Release verification checks expected
slots, terminal scheduler states, bindings, file integrity and report/download
consistency.

Keep raw inputs and source archives during development. Cleanup needs a separately
reviewed retention/restoration contract and explicit ownership/active-consumer
checks. The protocol does not authorise input deletion.

## 12. Decisions for this review

| Decision | Current review position | Consequence or unresolved detail |
| --- | --- | --- |
| D1. Panel breadth | Agreed: five references including a below-30% GC reference | M. florum L1 (about 27.0% published GC) is nominated for the fifth slot; nomination, exact source binding and byte admission remain to review |
| D2. Replication | Agreed: five sampling seeds | Proposed seed IDs 101/202/303/404/505; two reproducibility anchors and three technical repeats per order remain for review; current budget 166 for two versions |
| D3. Real companion | All 12 metadata-eligible study isolates after byte admission | Keep the known pilot visible and the two annotation-conflicted cases blocked; no outcome-based subset selection |
| D4. Error and bias arms | Agreed: deferred from v1 | Controlled errors, uneven within-replicon coverage, chimeras and composition-associated sequencing bias require a later amendment; zero current attempts |
| D5. Scientific endpoints | Existing 99% criterion primary; paper rule secondary; structural gate required for repeat/structure claims | Structural and canonical-agreement assessor specifications need a further methods review |
| D6. Configuration roster | Current Flye raw-mode and Raven versions for the foundation | Explicitly review whether to add a separate Flye high-quality configuration; +83 attempts, no replacement of the observed raw-mode results |
| D7. Delivery architecture | Agreed: complete Nextflow replacement with selectable benchmarks/scenarios | Port all in-scope old capabilities and the website bundle interface; preserve existing records; no permanent old controller or automatic reruns; parity acceptance and selector syntax still need review |

Agreement on the design should be followed by a checked, non-executable protocol
manifest and implementation plan. It is not itself permission to submit the suite.
