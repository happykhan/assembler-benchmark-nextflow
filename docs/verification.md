# Quick development verification

Verified on 11 November 2026 using Nextflow 25.10.2, the locked Linux64 Pixi
environment and the BMRC Cluster3 Slurm executor. This is a workflow check;
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
Version-specific isolated environments and additional assembler adapters follow
this initial slice.

The code and report are available locally. GitHub repository creation/upload was
attempted, but the command-line credential returned HTTP401 and was confirmed
invalid. Browser access was unavailable. No GitHub publication is claimed.

The compact machine-readable verification record is
[`evidence/quick-verification.json`](../evidence/quick-verification.json).
Full local run files are under `evidence/quick-run/v3/` and are ignored by Git.
