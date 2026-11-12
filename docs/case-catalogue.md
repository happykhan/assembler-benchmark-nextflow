# Selectable benchmark catalogue

Use Nextflow to inspect the admitted choices without downloading inputs or
scheduling scientific work:

```bash
nextflow run happykhan/assembler-benchmark-nextflow --list -profile native_tools
```

| Track | Selection | Scope |
| --- | --- | --- |
| Simulated | `--preset quick` | Two small read-length fixtures; workflow check only |
| Simulated | `--preset standard` | Admitted two-chromosome baseline; broader panel remains under review |
| General | `--track general --preset standard` | Exact published Wick/Holt 50, four reported workflows, 200 slots |
| Diagnostic | `--track diagnostic --preset standard --groups S1,S5` | Selected controlled scenario families |
| Real | `--track real --preset standard` | Admitted small-plasmid study pilot |

Diagnostic aliases are `plasmids` (S1), `coverage` (S2), `reproducibility`
(S3), `read-length` (S4), `linear` (S5), `errors` (S6), and `read-order` (S7).
New S6 error generation is deferred. S7 requires the admitted original source
under `--diagnostic_source_dir`; no substitute is simulated. Default S7 retains
four workflow configurations × four orders × three repeats = 48 slots.
Additional adapters or versions require explicit `--assemblers` selection.

The prospective five-family scientific design is the separate
[protocol review draft](benchmark-protocol-v1.md). Its low-GC reference,
five-seed panel and broader repeat/composition scenarios are not silently
admitted by the migration. There are no hybrid or metagenomic tracks.

Select cases and exact versions, or inspect their frozen slots before execution:

```bash
nextflow run happykhan/assembler-benchmark-nextflow \
  --track diagnostic --preset standard --groups S5 --assemblers raven-1.8.3 \
  --plan_only -profile native_tools --outdir results/plan-linear
```

Unknown selections, changed source metadata, duplicate version identities and
missing/extra outcome slots fail validation. Every selected plan binds case
parameters, references, exact environments and resource policy. A new selection
requires a new output directory. See the [README](../README.md) for execution,
input-only preparation and sealed-results import.
