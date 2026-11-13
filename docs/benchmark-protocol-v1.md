# Scientific scope and measurement contract

This document replaces the earlier conflicting long-read-only draft. The current
product is a **single-isolate bacterial genome assembly benchmark** for short and
long reads, using real and simulated datasets. Hybrid and metagenomic workflows
are excluded. The architecture and acceptance requirements are in
[the refactor specification](refactor-specification.md).

## Comparisons

There are two primary result sections:

- **Broad benchmarks** compare eligible configurations across declared dataset
  collections. The Wick/Holt published long-read simulated collection remains
  scientifically distinct from newly generated inputs. A broad short-read
  collection needs suitable paired reads and references; it is not created by
  re-labelling the long-read collection.
- **Targeted scenarios** ask specific questions about plasmids, GC/composition,
  repeats/structure, read quality/sampling and reproducibility. Shared baselines
  can belong to several scenarios without duplicate input generation or execution.

Read technology and source kind are explicit dataset properties and report
filters. Real and simulated observations remain separately labelled within
comparisons. Scenario pages state their question, conditions, dataset scope,
applicable workflows, metrics and units. There is no overall winner score.

The earlier discussion's examples of 400 simulated and 100 real datasets were
illustrations of scale, not an agreed scientific run budget. The current
refactor is validated on small representative cases. It does not authorise a full
panel run. Existing scientific recipes may remain in the catalogue without being
executed during software validation.

## Scientific units and identity

Biological isolates, sampling seeds, input order and technical executions are
separate axes. Five seeds do not create five independent biological isolates.
A technical repeat reuses the same input bytes. A deliberate read-order transform
preserves complete FASTQ records, including qualities, identifiers and duplicate
multiplicity, while changing their order. Its recipe and multiset/order
fingerprints must be explicit.

Each case declares its dataset/reference and input recipe. A fixed scientific
identity prevents a changed recipe from silently reusing an existing experiment's
case ID. Workflow configuration identity is stable across upgrades; the actual
software version and version order are recorded. A newer current result replaces
the previous result for that case/configuration/repeat, including a newly measured
failure. There is no operational result history in the product.

## Input preparation

References retain declared molecule inventories, accessions, lengths and native
topologies. Real inputs require explicit sample/reference identity and file
integrity checks. A polished reference remains a comparator whose confidence and
construction limitations must be stated; it is not automatically error-free truth.

Simulation settings are explicit recipes, not inferred from labels. Native
long-read sampling uses exact per-molecule budgets, gamma lengths, bounded linear
starts or a maximum single circuit around a circular molecule, and both strands.
Its Q40 qualities are synthetic placeholders. Short-read simulation uses pinned
ART profiles and paired-end geometry. The initial HS25 PE150 recipe uses fragment
mean/SD 350/50 bp. ART total-depth convention, error defaults and boundary-limited
sampling have been checked against the actual pinned binary; actual realised
coverage and mate statistics are retained. ART does not silently inherit the
long-read circular-wrap policy.

Coverage and length contrasts state their controlled quantities. A bimodal
read-length contrast holds total sequenced bases fixed and reports both base and
read-count fractions. Relative plasmid-depth contrasts hold chromosome depth
fixed; their total whole-isolate base budget changes deliberately. GC comparisons
across different species are descriptive composition strata, since genome size,
repeats and replicon inventory also differ. They do not establish a causal GC
effect or realistic GC-dependent sequencing bias.

## Measurements and statuses

Metric methods and units travel with every measurement. Long-read completion
retains the fixed 99% longest-single-alignment criterion against tripled
references, with uncapped contiguity. Selected-alignment identity and maximum
indel are only reported under the method's measured-span rule. This is distinct
from total reference breadth and from exact-copy or output-agreement methods.

Short-read assemblies are normally fragmented. Their reference breadth is
explicitly the union of saved alignment intervals; assembly length/count/N50 and
longest-alignment metrics retain their own labels. A fragmented short-read
assembly is not automatically an execution failure. Reference agreement does not
establish structural correctness, physical circularity or independently validated
repeat resolution. Unmeasured endpoints remain absent/null, not pass.

Resource measurements remain separate from scientific recovery. Workflow wall
time includes verification, assembly and assessment while excluding download,
software preparation and scheduler waiting. Process-tree RAM states its sampling
method and scope. Comparisons retain their declared resource configurations.

| Status | Meaning |
| --- | --- |
| `not_applicable` | The declared workflow is ineligible; no scientific job is scheduled |
| `not_run` | Eligible work has no completed attempted measurement |
| `execution_failure` | The attempted workflow did not produce a completed assembly outcome |
| `assessment_failure` | Measurement failed; available assembly output is retained |
| `measured` | The stated metrics were successfully measured; recovery can still be incomplete |

Preparation/infrastructure errors and missing dependencies are not evidence of
sequence absence. Assessment failures never become inferred biological failures.
A replacement execution failure removes old success displays and artifacts for
that slot while leaving unrelated current results untouched.

## Outputs and acceptance

Scientific packages publish per case/configuration, independently of an optional
website. Each package has readable HTML, JSON and TSV measurements, experiment
and input descriptions, software configuration, method/unit labels, statuses and
available supporting artifacts using package-relative paths. A root catalogue
indexes current packages; collection/scenario summaries reference those shared
results. Exported subsets include their dependencies once and work without
original Nextflow work directories or the hosted website.

The website renders this contract and prepared visual assets. It does not run
assemblers, rescore sequences or search historical batches. Large reads, bulky
logs and operational work caches remain outside its compact payload. Cleanup is
explicitly scoped to owned operational artifacts and must not delete unrelated
shared data or current result dependencies.

Software acceptance includes genuinely offline execution after preparation,
shared-filesystem concurrency, invalid/interrupted input rejection, selected-only
scheduling, assembly cache reuse after assessment/rendering repairs, portable
copied reports, atomic current-result replacement, downgrade protection and
correct scientific labels. Passing old byte-for-byte website parity tests is not
an acceptance requirement for this refactor. Detailed results must be recorded
only after those checks have actually run.
