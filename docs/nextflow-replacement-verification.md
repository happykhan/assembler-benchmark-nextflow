# Nextflow replacement: scope and verification

The subsequent [Cluster 3 validation](cluster-validation-v2.md) completed Quick
and selected general/S5/S7 paths, including 31 verified outcomes and cache-resume
checks. The migration checks below remain the historical archive/parity evidence.

Checked on 12 November 2026. This document separates implemented workflow paths,
verified historical evidence and newly executed scientific benchmarks. The
[protocol v1 draft](benchmark-protocol-v1.md) is still under review. New scientific
executions remain paused; this migration does not authorise a new panel run.

## One entry point, selectable tracks

The ordinary Quick command is unchanged:

```bash
nextflow run happykhan/assembler-benchmark-nextflow --preset quick
```

The same workflow now selects the frozen general comparison or diagnostic families:

```bash
nextflow run happykhan/assembler-benchmark-nextflow \
  --track general --preset standard --outdir results/general --run_id general

nextflow run happykhan/assembler-benchmark-nextflow \
  --track diagnostic --preset standard --groups S5 \
  --outdir results/linear --run_id linear
```

`--groups linear` is the alias for S5. Other diagnostic aliases are `plasmids`
(S1), `coverage` (S2), `reproducibility` (S3), `read-length` (S4), `errors` (S6)
and `read-order` (S7). New S6 error runs are explicitly deferred; importing and
presenting historical S6 evidence remains supported. `--cases` and
`--assemblers` narrow the selected slots without changing the scientific endpoint.

Reviewing metadata does not require running these scientific paths:

```bash
nextflow run happykhan/assembler-benchmark-nextflow \
  --track diagnostic --preset standard --groups S5 \
  --plan_only -profile native_tools --outdir results/plan-s5

nextflow run happykhan/assembler-benchmark-nextflow \
  --track general --preset standard \
  --plan_only -profile native_tools --outdir results/plan-general
```

Plan-only validates and freezes the selection and receipts. It performs no input
download, simulation, assembly or assessment. `native_tools` uses available
Python rather than installing scientific environments for metadata review.

Existing evidence has an independent import path:

```bash
nextflow run happykhan/assembler-benchmark-nextflow \
  --import_bundle /path/to/frozen/bundle \
  --outdir results/import -profile native_tools
```

Import verifies and admits a sealed archive, then renders it. It neither discovers
new run directories nor submits jobs. No old repository or old Slurm controller
is a runtime dependency. Native exports contain `bundle/`; the renderer produces
`website/` separately. The complete backend archive is kept outside the public
website payload.

## Module and helper boundaries

| Layer | Responsibility |
| --- | --- |
| `main.nf` | Select import versus execution, connect channels and completion gates |
| `modules/local/preparation.nf` | Freeze selection, prepare environments, admit references/reads, simulate or prepare selected inputs |
| `modules/local/execution.nf` | Run pinned assemblers and dispatch the declared assessor |
| `modules/local/reporting.nf` | Export sealed results, admit existing bundles and render websites |
| `benchlib/` | Planning, input/provenance checks, assembler adapters, resource evidence and common native export |
| `diagnostic_core/` | Preserved exact-copy, repeatability, read-order and supplementary diagnostic methods |
| `reporting/` | Archive validation and presentation from sealed records; no scheduling or sequence analysis |
| `website/` | Frontend sources and verified built assets for tables, graphs and saved-coordinate views |
| `assets/general/`, `assets/diagnostics/` | Frozen selections and source metadata |

A reporting change has a separate source fingerprint from assembler execution.
Resuming to repair presentation must not invalidate an unchanged cached assembly.
Native export parses retained GFA into bounded, sequence-free graph models and
prepares figures/TSVs from source-bound saved PAF coordinates. Rendering consumes
those prepared files. It never invokes an assembler, mapper or sequence assessor.
Unknown graph origins remain unassigned; graph shape does not establish physical
circularity or sequence correctness. Recorded tripled reference coordinates
remain labelled as tripled in the saved-coordinate view.

## What was verified

### Historical complete release

The existing sealed general-200 release was admitted and rendered using only the
new repository's reporting package and frontend assets. The archive contains 13
historical batches and 2,494 manifest-bound files. Admission preserves every
source byte and checksum. The general set retains 50 datasets and 200 reported
outcomes, together with historical diagnostic and supplementary evidence.

The strict archive/parity suite passed **9 of 9 tests**. The full test:

- Imported the frozen archive without modifying source records or its manifest.
- Prohibited the renderer from opening the original source archive after import.
- Prohibited external subprocess execution during rendering.
- Compared every public HTML page, graph model, figure and TSV byte for byte
  against the previously verified website.
- Checked S5 and S7 routes, the 200-result general model, downloads and the static release gate.

The new website has 1,419 files and passes the 64 MiB total, 1,500-file and
5 MiB-per-file limits. Public payload files are unchanged. Differences are confined
to administrative inventories/byte totals and the absence of the old deployment's
private `.vercel/project.json` linkage. This verifies historical presentation
parity; it does not establish that all newly implemented scientific execution
paths have been run.

S5 linear-reference evidence and S7's 48 recorded runs remain present. S7 output
agreement and its secondary reference verdict stay separate. General homepage
performance, `/performance`, and `/aggregate` remain distinct from diagnostic
scenario plots. Historical S6 and supplementary results are retained despite the
pause on new error scenarios.

### Native result presentation

The ordinary archive suite passed eight tests covering immutable import, changed
records, unmanifested files, symlinks, frozen-slot mismatch, safe output handling
and rendering after original-source removal. Three additional presentation tests
passed for interactive GFA/saved-coordinate export, S7 endpoint separation and
terminal resource-failure accounting. The existing 20 result/assessment/export
tests also passed after integration.

The actual Nextflow native import path completed both `IMPORT_RESULTS` and
`RENDER_WEBSITE` with exit 0 on 12 November, using `native_tools` and no assembly
stages. Its trace records two completed tasks. A retained native real-pilot bundle
also rendered successfully with the static link and size gate. A synthetic metadata fixture proved that native graph and coordinate
rendering consumes prepared models without reparsing GFA or invoking analysis.
These are presentation checks, not new scientific assemblies.

### Earlier scientific/runtime evidence

The original Quick simulated workflow has recorded Pixi and Singularity execution
evidence, including equal input hashes and sequence outcomes across those paths.
Docker profile configuration was parsed; Docker execution was not tested on
Cluster 3. See [native runtime verification](native-entry-verification.md) and
`evidence/native-entry/verification.json` for the recorded scope.

Earlier whole-genome baseline and real-data pilot results remain documented in
[Standard baseline](standard-baseline.md), [assessment diagnosis](assessment-diagnosis.md)
and [real small-plasmid pilot](real-small-plasmid-pilot.md). Those earlier checks
must not be relabelled as complete verification of the replacement's newly added
scientific paths or the proposed broader panel.

## Reproduce the reporting checks

```bash
python3 -m unittest discover -s tests -p test_website_parity.py -v
python3 -m unittest discover -s tests -p test_native_presentation.py -v
python3 -m unittest discover -s tests -p test_results.py -v
```

The full historical test is optional because the complete archive is a separate
scientific artifact rather than a source-code dependency:

```bash
BENCHMARK_HISTORICAL_BUNDLE=/path/to/frozen/bundle \
BENCHMARK_HISTORICAL_SITE=/path/to/verified/site \
python3 -m unittest discover -s tests -p test_website_parity.py -v
```

The ordinary suite reports the full archive test as skipped unless that archive
is explicitly supplied. A skip is not a parity pass. Scientific run approval,
new reference admission and the final five-seed panel remain protocol-review
work; no fresh simulation, assembly or cluster submission was performed for the
reporting migration checks above.

## Final integration checks

The native general plan contains exactly 200 reported slots across 50 inputs.
The default S7 plan retains 48 slots; Flye default and meta configurations are
compared separately even though they share a versioned executable. Explicit
additional assembler selections receive their own declared slots. S5 retains
36 slots including its raw and polished Miniasm supplementary configurations.

Execution export checks the complete frozen case, assembler definition and
software-lock hashes, not just slot IDs. Raw Miniasm assemblies, phase receipts
and logs survive a failed polishing continuation. Final Plassembler constituents
are verified independently before normalised combined-output assessment.
Supplementary diagnostic mapping preserves its own failure state without
changing a completed exact-copy verdict.

The integrated ordinary suite finished with **176 passes and one explicit skip**
(177 tests). Supplying the complete external archive separately passed all nine
archive/parity tests, including that skipped full-archive case. The final
historical site has 1,419 files, 63,635,405 bytes and 711 HTML pages; all 15,117
local-link checks pass. Compact verification and metadata-only Nextflow traces
are retained in `evidence/nextflow-replacement-v1/`.
