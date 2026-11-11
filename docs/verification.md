# Quick development verification

Verified on 11 November 2026 using Nextflow 25.10.2, the locked Linux64 Pixi
environment and the BMRC Cluster 3 Slurm executor. This is a workflow check;
the fixture results establish no scientific ranking.

## Successful end-to-end run

`quick-v3` completed all 12 Nextflow tasks: one online reference preparation,
two simulations, four assemblies, four assessments and one export. All tasks
exited zero; all four assembly execution records and assessments completed.
Each case used exactly 6,000,000 read bases, and both assemblers received the
same read SHA256 within each case.

The exported manifest accounts for exactly four case/assembler slots. All 44
retained file checksums and all local links in the standalone report were checked.
Final assemblies, available graphs, execution/simulation/reference evidence,
alignments, mapper logs and tool logs are retained. Three fixture assemblies
were incomplete and one met the completion endpoint; these are explicit
measurements, not a reason to change the fixture or tune an assembler.

## Offline and resume

The same run was launched with `--offline -resume`. Reference preparation ran
again using only the checksummed shared cache; the remaining **11 tasks were
cached**, including all four assembler tasks. No assembly was resubmitted.
The complete bundle passed the launcher's independent checksum gate.

Cleanup was tested in dry-run mode against that completed run. It identified
291 work files totalling 40,349,331 bytes, while keeping the shared reference
cache and final bundle. No benchmark data was deleted. Temporary test fixtures
exercise the explicit confirmed-deletion path separately.

## Regressions and preserved development attempts

All **42 focused tests pass**, covering reference corruption/offline absence,
exact read budgets, seeded mode interleaving, genuine software failures, version
and evidence binding, alignment geometry, missing/extra result slots, mapper
working directories, cleanup ownership and concurrent launch/deletion guards.

Earlier attempts remain intact on the cluster and are excluded from scientific
comparisons. `quick-v1` exercised recorded software/resource failure handling:
Flye exceeded the initial 4 GB development allocation. Subsequent development
uses 16 GB for Flye; its parameters and input bytes were unchanged. `quick-v2`
completed all assemblies but exposed a mapper working-directory bug. The export
completion gate blocked that release. The fix uses an absolute final-assembly
path; `quick-v3` verifies the corrected integration.

## Boundaries

Only Linux Pixi/Slurm was integration-tested. Docker and Apptainer profile
definitions are present but have not been run. Standard is not admitted, real
data are not implemented, and structural correctness remains unmeasured.
Version-specific isolated environments are verified in the subsequent checkpoint
below. Additional assembler adapters remain future work.

The initial GitHub upload was blocked by an expired command-line credential.
After sign-in was restored, the verified project was published to the private
[GitHub repository](https://github.com/happykhan/assembler-benchmark-nextflow).
The full report bundles remain local/on-cluster; compact verification evidence
and reproducible source definitions are committed.

The compact machine-readable verification record is
[`evidence/quick-verification.json`](../evidence/quick-verification.json).
Full local run files are under `evidence/quick-run/v3/` and are ignored by Git.

## Version modules and frozen planning

The subsequent implementation is committed as `778e754`. All 69 focused tests
pass on the cluster. `quick-versioned-v2` completed 13 tasks, including independent
plan validation, four executions and four assessments using immutable IDs
`flye-2.9.6` and `raven-1.8.3`. Each version selected its own locked environment.
All four expected slots and all 44 retained-file checksums were verified.

`quick-selection-v1` then selected just `quick-bimodal` and the `raven` alias.
The frozen plan resolved that alias to `raven-1.8.3`; all six tasks and the single
execution/assessment completed. Compute-side environment installation was
disabled with `--no-install`. Both named environments and the tooling environment
also passed direct version checks with installation disabled.

The first version-module attempt is preserved as `quick-versioned-v1`. Pixi
failed in its path resolver before assembler invocation. Environments are now
prepared serially under a provisioning lock before any Nextflow jobs are
submitted. Successful or failed setup receipts are retained; assembler jobs
remain parallel, with queue capacity 1,000. No failed sequence outcome was
inferred from that infrastructure failure.

See [`evidence/modular-verification.json`](../evidence/modular-verification.json)
for plans, task accounting and checksums. At that checkpoint, Standard remained
a sourced proposal; the following checkpoint admits only its small baseline.

## Admitted whole-genome Standard baseline

`standard-baseline-v1` completed all 14 Nextflow tasks on Cluster 3: plan
validation, two whole-reference preparations, two simulations, four executions,
four assessments and export. The two original whole circular chromosomes are
admitted with archive, accession, molecule, sequence and canonical FASTA bindings.
Quick remains a separate, unchanged 200 kb linear fixture.

The independent read-only input audit checked every realised read against its
declared strand-specific circular source coordinates, including budget trimming.
All 19,784 reads / 197,435,850 bases matched exactly. The datasets contain
126,468,180 and 70,967,670 bases respectively: exactly 30× each. All 62 observed
circular-wrap reads matched their references. The audit ran as Slurm job 35267183,
completed exit 0:0 in 12 seconds; its source and raw result are retained.

All four assembler executions and assessments completed. Every assembly was
incomplete under the fixed 99% longest-alignment endpoint. Identity was 1.0 on the
eligible longest alignments. These measurements are retained without parameter
tuning or causal claims about the reasons for incompleteness. This is baseline
validation, not the completed scientific panel or a headline ranking.

A reporting-only repair added explicit purpose/headline exclusion fields to TSV
and manifest exports. Resume reused all 13 compute tasks and submitted only a
new export. Result objects and all numerical scores were verified unchanged.
HTML, JSON, TSV and manifest consistently exclude the baseline from headlines.
All 44 retained-file checksums and local report links passed; all 85 tests passed.

Cleanup was checked in dry-run mode only. Work and frozen inputs remain on the
cluster; reference caches and final assemblies/graphs are retained. Source
receipts, the full-input audit and compact verification are tracked in Git;
the full local report bundle is under the ignored directory
`evidence/standard-runs/standard-baseline-v1/bundle/`.

- [Reference admission](reference-admission.md)
- [Baseline verification](../evidence/standard-baseline-verification.json)
- [Full-input audit](../evidence/standard-input-contract-audit.json)
