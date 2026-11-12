# ATCC25922 real-data small-plasmid pilot

This is a new comparison using the deposited data from Johnson, Soehnlen and
Blankenship (2023), DOI [10.1099/mgen.0.001024](https://doi.org/10.1099/mgen.0.001024).
It is not a reproduction of the original published subset percentages. The input
policy is full archive ONT reads, without filtering, subsampling or simulation.
Only this isolate is admitted; the full cohort stays proposed.

## Frozen inputs

- BioSample: SAMN32977649; ONT run: SRR23290062.
- Source assembly: GCA_028596225.1, same BioSample.
- Chromosome: CP117235.1, 5,132,219 bp.
- Plasmids: CP117234.1, 1,919 bp; CP117233.1, 3,173 bp;
  CP117236.1, 24,185 bp; CP117232.1, 48,488 bp.
- Read archive: 821,540,769 bytes; publisher MD5
  `2934c206376021f54f34e97d033b5bd8`.
- Parsed reads: 165,764; total bases: 867,904,341; N50: 10,414 bp;
  lengths: 103–92,708 bp; decompressed bytes: 1,741,056,684.
- Compressed SHA256:
  `2d954c5bb05b1d46400b3d1738466304f5bd91afe41a93ca71ba1c0dccde0422`.
- Decompressed SHA256:
  `be9fbc1d265d8a7b056e3d764188cf60c0fbf2da5a99f3379fc7d8b450905519`.

Admission verifies the archive's publisher checksum/size, gzip integrity, full
FASTQ syntax, read/base totals, and compressed/decompressed/header hashes.
Decompressed header, sequence and quality bytes remain unchanged. The complete
reference archive passes its publisher MD5; versioned molecule inventories,
lengths, topology and same-sample binding match frozen ENA/NCBI metadata.
Canonical and per-molecule sequence hashes are retained. Reference admission
initially did not establish independent ENA FASTA sequence equality; see any
subsequent audit separately rather than rewriting that receipt.

The deposited references partly derive from the tested assembler families and
were polished with other sequencing evidence. They are useful same-isolate
comparators, not independently established error-free truth. Illumina accessions
are provenance only and are never used as assembly inputs.

## Native Nextflow execution

```bash
nextflow run happykhan/assembler-benchmark-nextflow -latest \
  --track real --preset standard --cases johnson-atcc25922-full \
  -profile bmrc,pixi --outdir results/real-plasmid-pilot --run_id real-plasmid-pilot
```

The real-input branch bypasses `SIMULATE_READS` and feeds the existing immutable
assembler adapters. Flye 2.9.6 and Raven 1.8.3 each receive the same full-read hash.
There is no parameter search or automatic assembler retry. Each has four CPUs,
16 GB and a four-hour limit. Environment provisioning, downloads, input preparation
and read-support mapping are separate from measured assembly/assessment time.

Online preparation downloads only the selected data. Offline mode verifies the
same archive and decompressed hashes before using cached inputs. A modified cache,
wrong BioSample/run, changed admission receipt or mismatched molecule inventory
stops the workflow. Raw inputs are retained; no automatic cleanup is implemented.

## Distinct assessments

1. `wick-longest-alignment-v1`: unchanged fixed 99% completion using the longest
   single alignment against tripled references, uncapped contiguity, and measured
   identity/indels only. The chromosome and all four plasmids are assessed.
2. `johnson-2023-summed-block-rule-v1`: native reference as query, draft assembly
   as target, current pinned minimap2 `asm5`; strictly >90% summed alignment blocks
   per draft contig, with the published fragmented fallback. Multiple recovering
   draft contigs and the >1 Mb chromosome-incorporation heuristic are separate
   flags. Blocks are not deduplicated. It assesses the four declared plasmids.

The second is a tested implementation of the stated paper rule, not literal
replay of all historical software. Explicit no-hit rows mean below threshold;
missing/truncated PAF query accounting is an assessment error. A no-hit row is
not confused with the supporting R code's special filtering of size-zero targets.
Neither metric proves structural correctness. A paper-rule measurement error preserves any
valid primary measurement and blocks the complete real-pilot export gate.

A separate native-reference read mapping suppresses secondary alignments while
retaining split alignments. It reports interval-union breadth, distinct mapped
read IDs and summed aligned-target depth for each molecule. This is read support,
not assembly recovery, unbiased copy number or independent reference truth.

The bundle retains final FASTA/available GFA, both assessment PAFs, input-support
PAF and diagnostics, logs, immutable plan, admission/provenance bindings, TSV/JSON,
standalone HTML and checksums. The real-data completion gate requires both
assessments and read-support diagnostics, or a recorded genuine software failure
with no sequence verdict.


## Verified pilot results — 12 November 2026

Both immutable assembler versions completed on the same full-read SHA256.
No assembler retry was performed. The two original execution JSONs and final
assembly hashes remain identical after assessment/reporting improvements.

| Native molecule | Flye 2.9.6 longest-alignment contiguity | Flye paper rule | Raven 1.8.3 longest-alignment contiguity | Raven paper rule |
| --- | ---: | --- | ---: | --- |
| Chromosome, 5,132,219 bp | 100.00% | Not applicable | 100.00% | Not applicable |
| Plasmid, 1,919 bp | 106.98% | Recovered | 0.00% | Below threshold |
| Plasmid, 3,173 bp | 123.57% | Recovered | 0.00% | Below threshold |
| Plasmid, 24,185 bp | 87.34% | Recovered through fragmented fallback | 100.00% | Recovered |
| Plasmid, 48,488 bp | 100.00% | Recovered | 100.00% | Recovered |

Contiguity above 100% is retained intentionally by the uncapped metric; it is not
proof of structural correctness. The paper rule's fragmented fallback is not
merged into the single-alignment verdict. Flye produced eight final contigs;
Raven produced three. These are one-isolate pilot observations, not a ranking or
a reproduction of the study's historical percentages.

Input support was substantial for all four plasmids:

| Molecule | Distinct mapped read IDs | Reference breadth | Mean aligned-target depth |
| --- | ---: | ---: | ---: |
| Chromosome | 89,443 | 99.99998% | 122.01× |
| 1,919 bp plasmid | 31,493 | 99.68734% | 28,526.45× |
| 3,173 bp plasmid | 36,976 | 99.71636% | 32,438.87× |
| 24,185 bp plasmid | 3,650 | 99.96279% | 1,042.35× |
| 48,488 bp plasmid | 3,234 | 99.97938% | 798.67× |

Native circular ends, mapping thresholds and repeat/split alignments affect these
diagnostics. They establish read support, not unbiased plasmid copy number. They
also prevent confusing absent input support with the observed Raven recovery
result. No causal parameter intervention or tuning was performed.

### Verification and retained evidence

- Nine Nextflow stages, including one real-input preparation stage and **no
  simulation stage**; both completed assemblers reused their original cached
  outputs when the reporting/diagnostic stages were developed.
- All nine stages cached on the final resume, with no new job submissions.
- Eight final compute-job records terminal `COMPLETED`, exit `0:0`.
- Two assembled/assessed slots, ten TSV molecule rows, 32 retained bundle files;
  every declared checksum and the complete bundle file inventory verified.
- Independent arithmetic rechecks of longest alignments, identity/indels, strict
  thresholds, paper-rule sums/flags and read-support breadth/depth.
- Local report links resolve, and the exported JSON/TSV identify the real track,
  exact run, sample, reads, references and versions.
- **120 scoped tests passed**, including wrong BioSample, altered cache, truncated
  FASTQ, corrupt transfer, missing PAF accounting and independent metric failures.
- A separate cold-download test reproduced the admitted compressed/decompressed
  hashes. The initial plain streaming transfer was rejected when truncated;
  no assembly consumed that failed transfer. The downloader prefers an existing
  curl client for negotiated streaming, with bounded validated HTTP ranges as a
  standard-library fallback. All paths require exact final size, MD5 and SHA256.
- All four plasmid sequences also match independently retrieved ENA FASTAs.
  The independent chromosome FASTA transfer was incomplete; that does not replace
  or invalidate the complete publisher-checksummed NCBI reference archive.

The initial pilot consumed the byte-admitted cache. Online preparation was
checked separately from a fresh archive cache, using the same input module and
locked Python environment. This is not a claim that every runtime/site has been
cold-download tested. The full real-data pilot was verified with Pixi/Slurm;
Singularity also passed the updated simulated Quick regression and cached resume.
Docker remains a configuration-only profile on this cluster.

Compact proof files and the independent verifier are under
[`evidence/real-data/atcc25922-pilot`](../evidence/real-data/atcc25922-pilot).
The full standalone bundle is retained on Cluster 3 at
`/well/aanensen/users/rva470/assembler-benchmark-real-pilot-v1/results/full-pilot-v1/bundle`
and in the ignored local `evidence/real-runs/atcc25922-full-v1/bundle`.
Raw inputs, original attempts and source snapshots remain on the cluster.
No input cleanup or website publication was performed.
