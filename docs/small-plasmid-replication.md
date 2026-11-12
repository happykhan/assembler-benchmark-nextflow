# Real-data small-plasmid study: admission proposal

**Cohort metadata mapped; one-isolate pilot admitted separately.** The full 14-isolate
manifest remains a proposal. The [ATCC25922 pilot](real-small-plasmid-pilot.md) now
has byte-verified reads and references and a native Nextflow real-input branch.
This is a separate real-data
case within the plasmids group, alongside the simulated cases. It does not change
Quick, the simulated Standard baseline, or their results.

[Johnson, Soehnlen and Blankenship (2023), *Long read genome assemblers struggle
with small plasmids*](https://doi.org/10.1099/mgen.0.001024) provides relevant
single-isolate ONT datasets and deposited assemblies from the same BioSamples.
The proposed inventory covers all 14 isolates and 33 native plasmids, including
11 below 10 kb. Sources were checked on 12 November 2026. The
[proposed manifest](../assets/real-data/small-plasmids-paper.json) contains exact
run accessions, archive FASTQ URLs, publisher MD5s, compressed byte counts,
versioned reference molecules, inferred supplementary-contig mappings and
remaining blockers. No raw-read download or assembly was started for this work.

Only ONT reads can be assembly inputs. Illumina accessions are retained solely as
provenance for how the authors built/polished their reference assemblies. There
are no hybrid or metagenomic benchmark arms.

## Read and reference inventory

The three paper BioProjects are [PRJNA929966](https://www.ncbi.nlm.nih.gov/bioproject/PRJNA929966),
[PRJNA288601](https://www.ncbi.nlm.nih.gov/bioproject/PRJNA288601) and
[PRJNA812922](https://www.ncbi.nlm.nih.gov/bioproject/PRJNA812922). The latter two
also contain unrelated surveillance data. Project membership alone never selects
benchmark inputs: the manifest freezes the exact 14 BioSamples and ONT runs.

Every assembly, molecule and read run below was joined through the same BioSample,
not just a species or strain name. The reference column includes the exact assembly
version; its complete molecule inventory is in the JSON. Plasmid lengths below
come from the pinned author supplementary table and match deposited sequence
lengths. The two NG cases have an unresolved molecule-label conflict described
below.

| Isolate | BioSample | ONT run | Same-sample assembly | Plasmid lengths (bp) |
| --- | --- | --- | --- | --- |
| 2020QW-00078 | SAMN17608176 | [SRR23291426](https://www.ebi.ac.uk/ena/browser/view/SRR23291426) | GCA_022024795.3 | 34,331, 97,090, 194,062 |
| 2021QW-00045 | SAMN21919088 | [SRR23291425](https://www.ebi.ac.uk/ena/browser/view/SRR23291425) | GCA_021904535.3 | 97,090, 190,147 |
| 2021QW-00056 | SAMN21919093 | [SRR23291424](https://www.ebi.ac.uk/ena/browser/view/SRR23291424) | GCA_021904655.3 | 12,268, 95,985 |
| 2021QW-00057 | SAMN22066472 | [SRR23291423](https://www.ebi.ac.uk/ena/browser/view/SRR23291423) | GCA_020362645.3 | 2,101, 4,063, 4,084, 4,715, 46,161, 118,339 |
| 2022NG-0032 | SAMN33482239 | [SRR23640110](https://www.ebi.ac.uk/ena/browser/view/SRR23640110) | GCA_029378455.1 | 4,153 |
| 2022NG-0076 | SAMN33482240 | [SRR23640109](https://www.ebi.ac.uk/ena/browser/view/SRR23640109) | GCA_029378435.1 | 4,207 |
| 2022QW-00133 | SAMN32885235 | [SRR23291422](https://www.ebi.ac.uk/ena/browser/view/SRR23291422) | GCA_028596045.1 | 27,080, 43,879 |
| ATCC14028 | SAMN32977646 | [SRR23290065](https://www.ebi.ac.uk/ena/browser/view/SRR23290065) | GCA_028596185.1 | 93,832 |
| ATCC14458 | SAMN32977647 | [SRR23290064](https://www.ebi.ac.uk/ena/browser/view/SRR23290064) | GCA_028596165.1 | 4,326, 4,439, 15,773, 30,891 |
| ATCC23235 | SAMN32977648 | [SRR23290063](https://www.ebi.ac.uk/ena/browser/view/SRR23290063) | GCA_028596145.1 | 27,269 |
| ATCC25922 | SAMN32977649 | [SRR23290062](https://www.ebi.ac.uk/ena/browser/view/SRR23290062) | GCA_028596225.1 | 1,919, 3,173, 24,185, 48,488 |
| ATCC25923 | SAMN32977650 | [SRR23290061](https://www.ebi.ac.uk/ena/browser/view/SRR23290061) | GCA_028596245.1 | 27,490 |
| ATCC33090 | SAMN32977651 | [SRR23290060](https://www.ebi.ac.uk/ena/browser/view/SRR23290060) | GCA_028596125.1 | 104,612 |
| ATCCBAA2146 | SAMN32977652 | [SRR23290059](https://www.ebi.ac.uk/ena/browser/view/SRR23290059) | GCA_028596205.1 | 2,014, 85,160, 117,755, 140,825 |

The complete ONT download inventory totals **10,933,444,482 compressed bytes**
(about 10.18 GiB). That excludes reference archives, decompressed reads, work
folders, mapping files and assembly outputs. Each read file's publisher MD5 is
known; downloaded-byte SHA256 and recomputed FASTQ statistics are intentionally
null until preparation verifies the actual file. ENA archive-generated FASTQ is
not assumed byte-identical to the authors' submitted combined FASTQ.

The paper reports R9.4.1 flowcells, Rapid Barcoding SQK-RBKP004, an Mk1C, and
Guppy 6.4.2 HAC basecalling with minimum Q8. Archive experiment metadata and the
paper describe related material, but archive FASTQ headers/processing have not yet
been inspected to establish equivalence to those exact HAC inputs.

## Discrepancies that must remain visible

The author [supporting files are pinned to commit
`107c3dd3865cff8ab5bd86ef70249a65b465aa9c`](https://github.com/johnsonj161/for_publications/tree/107c3dd3865cff8ab5bd86ef70249a65b465aa9c/Long%20read%20genome%20assemblers%20struggle%20with%20small%20plasmids).
The second CSV contains all 33 plasmids and resolves three discrepancies in the
article's Table 1:

| Isolate | Article Table 1 | Pinned supplementary-data-2 and same-sample deposited lengths |
| --- | --- | --- |
| ATCC25922 | 93,832 bp medium plasmid | 48,488 bp (`CP117232.1`) |
| ATCC25923 | 27,490 and 27,080 bp plasmids | One 27,490 bp plasmid (`CP117231.1`) |
| 2022QW-00133 | One 43,879 bp plasmid | 43,879 and 27,080 bp plasmids (`CP117204.1`, `CP117205.1`) |

Do not combine the paper table with archive records to create a synthetic truth
inventory. Author contig IDs in the CSV map to archive molecules by same isolate
and unique exact length. This is a candidate mapping, **not proof that their
original author FASTA bytes equal the deposited sequence**.

The two *N. gonorrhoeae* deposits have an additional source annotation problem:

| Isolate | Archived record labelled chromosome | Archived record labelled plasmid |
| --- | --- | --- |
| 2022NG-0076 | `CP119139.1`, 4,207 bp | `CP119140.1`, 2,168,363 bp |
| 2022NG-0032 | `CP119141.1`, 4,153 bp | `CP119142.1`, 2,167,441 bp |

Both ENA and NCBI summaries report these labels; an original EMBL header excerpt
also confirms the first. The small lengths match the authors' reported plasmids,
so the manifest explicitly distinguishes `archive_role` from
`proposed_biological_role`. It records a conflict instead of changing the source
annotation or quietly treating the larger record as the chromosome. These two
cases remain blocked pending an explicit, evidenced interpretation. The remaining
12 isolates can be prepared independently without resolving those two records.

## Reproduction and modern comparison are separate runs

The paper used three Trycycler 0.5.3 subsets per isolate and older assembler
versions. Exact historical subset read IDs and hashes are not provided in the
retrieved supporting files. A fresh `subsample --count 3` call alone does not
establish that the original subsets have been reproduced. The supplied code also
requires an audit against the versioned tool interfaces before literal replay;
for example, the Miniasm/Minipolish snippet passes a PAF-named intermediate.

A modern comparison can instead freeze new, explicitly documented input
selections and the repository's admitted assembler versions. It must say
**new comparison using the study's deposited data**, preserve its own seeds/read
IDs/hashes and never present its values as reproduced published percentages.
Full-read inputs and regenerated subsets would be distinct cases, with separate
immutable run IDs. No parameter search is needed to make the dataset useful.

The paper reference assemblies were built from consensus of multiple drafts and
polished using ONT and Illumina evidence. They partly depend on the assembler
families being tested. We retain that dependency and reference-construction
history rather than presenting them as independent, error-free truth.

## Two explicit assessment definitions

The paper's historical endpoint sums PAF alignment-block lengths and uses a
**strictly greater than 90%** threshold, with per-draft-contig filtering and a
fragmented-contig fallback in the pinned R code. It can count overlapping or
repeated alignment contributions; it is not deduplicated sequence breadth.
Its chromosome-incorporation heuristic uses a draft-contig length over 1 Mb,
and its duplicate flag concerns multiple recovering draft contigs. The supporting
implementation needs dedicated fixtures before an executable historical assessor
is admitted.

The existing benchmark instead uses **at least 99% in the longest single
alignment against a tripled reference**, with uncapped contiguity. Identity and
indels remain measured fields only. Report the two endpoints in separate columns
with distinct identifiers and versions. Neither one proves overall structural
correctness. Absence of a report or a failed measurement remains unresolved,
never a missing-plasmid verdict.

## Minimal integration slice

The proposed first real-data pilot is **ATCC25922 / SRR23290062**: one same-sample
chromosome and four native plasmids, including 1,919 and 3,173 bp plasmids plus
24,185 and 48,488 bp controls. Its compressed ONT file is 821,540,769 bytes.
This is an admitted development pilot in the real-input track, excluded from
headline comparisons and from the default simulated Standard selection.

1. Prepare only the selected run and versioned reference set. Preserve source
   archives, publisher checksums, original headers and molecule order; calculate
   compressed/decompressed SHA256, sequence SHA256 and exact FASTQ statistics.
   Reconcile assembly report, sequence inventory, source BioSample and any
   explicit role overrides in a receipt.
2. Select a declared full-read or frozen-subset policy, bind exact read bytes to
   every assembler execution, and preserve preparation and failed attempts.
   Reuse those admitted bytes in online and offline modes.
3. Add a real-read input branch that feeds the existing assembler adapter tuple
   after preparation. It bypasses simulation. A separate real-data manifest and
   plan receipt must bind dataset/run/BioSample/reference and assembler versions;
   do not weaken the existing simulation admission gate.
4. Assess the native chromosome and every declared plasmid independently. Export
   input provenance, execution state, measurement state and molecule outcomes in
   the website-independent bundle and standalone report. Keep a future historical
   assessor separate from the existing contiguity method.
5. Verify an initial end-to-end real pilot before scaling to the 12 annotation-
   consistent isolates; include the two conflicting NG cases only after their
   source role issue is resolved. Cleanup remains dry-run advice until checksummed
   inputs/results, completed consumers and a restoration route are verified.

The metadata-only inspection is available now:

```sh
python3 bin/inspect-real-data.py
```

It checks exact BioSample joins, versioned accessions, inventory totals, source
receipt hashes and explicit annotation conflicts. It reports `executable: false` and admission blockers for the full cohort.
Passing this metadata check does not admit that cohort. The separate
`assets/real-pilot.json` and byte-verified admission receipts enable only the
ATCC25922 case through `--track real --preset standard`.

## Provenance and reuse

Small original ENA/NCBI metadata responses are frozen under
[`evidence/real-data/small-plasmids`](../evidence/real-data/small-plasmids).
The manifest binds each response's SHA256, byte count and retrieval URL. Header
excerpts are identified as excerpts. Supporting source CSVs/code are cached locally
under ignored `references/study-evidence/small-plasmids/`; their immutable URLs,
SHA256 and byte counts are in the manifest, without vendoring executable author
code. No read sequences are stored in Git.

The article states Creative Commons Attribution. No dataset-specific licence is
asserted for the supporting repository or deposited reads/references. Record
[NCBI molecular-data usage policy](https://www.ncbi.nlm.nih.gov/home/about/policies/#molecular)
and original author/archive attribution with all future receipts. A newer or
species-matched reference must not silently replace these versioned deposits.
