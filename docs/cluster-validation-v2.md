# Cluster 3 end-to-end validation — 12 November 2026

The authorised small validation is complete. This verifies selected execution
paths, not the full five-seed scientific panel or every assembler/scenario
combination. The existing published 200-outcome archive was not rerun or changed.

| Selection | Outcomes | Verification |
| --- | ---: | --- |
| Quick: baseline and bimodal, Flye and Raven | 4 | Complete; all 14 tasks cached on resume |
| Quick regression after infrastructure fixes | 4 | Complete; all 14 tasks cached on resume |
| General: two frozen Wick/Holt datasets, four workflows | 8 | Complete; published read/reference bytes verified |
| S5: native-linear case, Raven/Plassembler/Miniasm + Minipolish | 3 | Complete; exact assessment and supplementary mapping completed |
| S7: Raven, four orders, three repeats | 12 | Complete; input multiset equivalence verified |
| **Total** | **31** | **No unresolved slots** |

These runs used Nextflow 25.10.2, Slurm and pinned Pixi environments. This is not
a new container-profile validation. Assemblies retained the declared four CPUs,
16 GB and time limits. Final trace IDs, including cached IDs, were checked against
terminal Slurm accounting: all are COMPLETED with exit 0.

## Scientific outcomes

Execution success is separate from sequence recovery. The general pilot has two
fully complete, two chromosome-complete and four incomplete outcomes. An
independent saved-PAF audit agrees with all 20 molecule measurements, including
tripled-reference coordinates, uncapped longest-alignment contiguity, the 99%
threshold and conditional identity/indel measurements.

All three S5 strict exact-copy verdicts are fail; the workflow completed and
preserves those results. S7 reports **Order-associated output difference** across
12 runs. Its secondary reference checks remain separate from that agreement
verdict. Neither result was retried to improve its biological score.

## Repairs exercised on the cluster

- General resource lookup accepts default memory when a per-tool map is absent.
- Shared reference admission uses atomic directory locks, unique transfer
  candidates and verified publication that cannot overwrite admitted bytes.
- Frozen JSON plans are eagerly initialised before parallel channel consumers.
  S7 resume reused nine completed assemblies and ran only three missing slots.
- Batch execution supplies a TERM default for Minipolish version detection.
- Healthy peers finish after a task failure; automatic retries remain disabled.
- Plassembler graphs are retained under their actual output prefix, scoped to
  final plasmids. Empty graphs remain recorded empty artifacts. This reporting
  repair reused all 11 general/S5 assemblies from cache; execution hashes,
  sequence verdicts, replicon measurements and exact evaluations are unchanged.

Initial infrastructure attempts, interrupted peer jobs, original source and
pre-repair bundles/traces are preserved under
`/well/aanensen/users/rva470/assembler-benchmark-validation-20261112/` in
`run-attempts/`, `source-attempts/` and `input-attempts/`. No active inputs were
deleted. Raw Miniasm is retained inside the polished workflow, not counted as an
extra general outcome. Plassembler retains its final plasmids and chromosome.

## Evidence and remaining scope

Compact manifests, plan/runtime bindings, terminal accounting, traces, independent
PAF audit and retention comparisons are in
[`evidence/cluster-validation-v2/`](../evidence/cluster-validation-v2/).
Desktop/mobile checks cover homepages, scenario/performance pages, aggregate,
execution details, graph controls, TSV downloads and figures. The ordinary suite
passes 184 tests with two explicit skips (186 total); the optional real Nextflow
channel/resume regression also passed separately.

The broader protocol remains under review: five seeds, a low-GC reference and
deferred error scenarios. Validation does not authorise starting that full panel
or replacing the live historical website with these selected pilot reports.
