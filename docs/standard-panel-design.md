# Initial Standard panel proposal

Proposed on 11 November 2026. **Not admitted, not executable and not run.**
This document specifies the next scientific slice after Quick. It concerns
single-isolate bacterial long-read assembly using simulated reads. There is no
hybrid or metagenomic track. The machine-readable candidate list is
[`assets/standard-candidates.json`](../assets/standard-candidates.json).

## References: four whole genomes, not Quick fragments

Start with four established laboratory, food-associated or environmental model
references. Retain each genome's original replicon complement and topology.
Keep native sequences and replicon inventories. Quick's 200 kb linear fixture
remains excluded from Standard.

| Proposed reference | Frozen-record candidates | Why include it; primary evidence |
| --- | --- | --- |
| *Bacillus subtilis* 168 | Chromosome AL009126.3 / NC_000964.3; use the same source archive already verified for Quick, without slicing it. | Existing source continuity and a middle-composition chromosome. The reference-maintenance paper identifies [AL009126.3](https://doi.org/10.1111/1751-7915.13043); an earlier primary description reports approximately [43.5% GC](https://doi.org/10.1016/S0014-5793(98)00620-6). Recompute composition from the frozen bytes. |
| *Lactococcus lactis* IL1403 | Chromosome NC_002662.1 / AE005176; original assembly GCA_000006865.1. | Lower-composition, plasmid-free dairy laboratory model. The [genome paper](https://doi.org/10.1101/gr.169701) reports 2,365,589 bp and approximately 35.4% GC; [NCBI BioProject 72](https://www.ncbi.nlm.nih.gov/bioproject/72) documents strain origin, plasmid-free status and the complete assembly. A later IL1403 resequence also exists, so never replace this record silently. |
| *Micrococcus luteus* NCTC 2665 | Original complete chromosome CP001628.1; candidate RefSeq alias NC_012803.1, to bind explicitly during admission. | High-composition reference. The [original genome study](https://doi.org/10.1128/JB.01254-09) reports a single circular chromosome of 2,501,097 bp and 73% GC. [JGI's original project](https://genome.jgi.doe.gov/portal/miclu/miclu.info.html) identifies CP001628 and its finished status; the [nucleotide record](https://www.ncbi.nlm.nih.gov/nuccore/CP001628) identifies version 1. Do not substitute a newer same-strain assembly. |
| *Lactiplantibacillus plantarum* WCFS1 | Corrected chromosome AL935263.2; native plasmids pWCFS101/102/103, published under CR377164/CR377165/CR377166. Resolve and freeze the plasmid versions before admission. | Native small and medium plasmids plus a chromosome. The [2012 resequencing paper](https://doi.org/10.1128/JB.06275-11) reports the corrected 3,308,273 bp, 44.5% GC chromosome and its accession. The [plasmid study](https://doi.org/10.1128/AEM.71.3.1223-1230.2005) documents three native plasmids of 1,917, 2,365 and 36,069 bp with their accessions. Confirm that the chosen chromosome/plasmid records form the declared archival reference set. |

These are candidate records, not downloaded payloads or validated biological
ground truth. Some direct NCBI pages were inaccessible during this review;
accession-to-molecule bindings and payload hashes still require admission.
Historical references can define exact simulation truth once frozen, but this
does not prove the biological reference is error-free or suitable as truth for
a later real-data isolate. The original WCFS1 chromosome was reported as
3,308,274 bp; the corrected record differs. That is a concrete reason to retain
accession versions, rather than use a species/strain name as an input identity.

Four references provide an initial composition range of roughly 35–73% GC,
not an exhaustive bacterial GC panel. Baseline results across species are
**descriptive composition strata**: genome size, repeats and replicon complement
are confounders. They cannot establish that GC itself caused a difference.

## Controlled conditions and an initial run budget

Use an error-free, uniformly sampled baseline to study intrinsic assembly
behaviour. Proposed baseline settings are 30× per replicon, a single long-read
length distribution centred on 10 kb, and three independent simulation seeds.
These values are proposed workload choices, not empirically optimised settings
or claims about a particular Nanopore chemistry. Freeze the exact distributions
and realised budgets before comparing assemblers.

| Group | Initial contrast | Inputs and accounting |
| --- | --- | --- |
| GC/composition | The four whole-genome baselines under the same simulation recipe. | Four references × three independent seeds = 12 simulations. Report measured GC, size and repeat inventory alongside outcomes. Do not pool them as an isolated causal GC experiment. |
| Read quality/sampling | On *B. subtilis*: lower coverage 10×; shorter distribution centred on 2 kb at 30×; bimodal mixture with 50% of bases from the short mode at 30×; a separately specified controlled error arm. | Four additional conditions × three seeds = 12 simulations. Hold total sequenced bases fixed for length-mixture contrasts; report both read-count and base fractions. Coverage and error contrasts change one designated property. |
| Plasmids | On WCFS1: baseline per-replicon coverage, then lower and higher plasmid coverage relative to a fixed chromosome budget. | Two additional relative-depth arms × three seeds = 6 simulations. Propose plasmid:chromosome coverage ratios 0.25 and 4, with chromosome coverage 30×. The total whole-isolate base budget consequently changes and must be reported; this is not the fixed-base length experiment. |
| Repeats/genome structure | Use native repeat contexts in *B. subtilis*: the existing short-read arm, baseline, and a longer distribution centred on 20 kb, all at the same base budget. | One additional long-read condition × three seeds = 3 simulations. Measure the reference's actual repeat intervals and realised read spans before interpreting recovery; do not assume a distribution parameter proves a repeat was bridged. |
| Reproducibility | For one frozen *B. subtilis* baseline read set: three identical-input executions; two additional deterministic read orders, each with three executions. | The original baseline execution is reused. Add 2 repeated executions plus 6 reordered-input executions per assembler/version. Keep independent sampling, repeated execution and changed read order as distinct axes. |

This is **33 unique simulations**, plus two reordered derivatives of an existing
read multiset. With the reproducibility executions, it is **41 assembly attempts
per assembler/version**, or82 attempts for the initial two admitted versions.
The five groups reference shared cases; they do not duplicate baseline inputs or
count the same assembly twice. The manifest must store group memberships
separately from unique case/attempt IDs. Adding one new version would therefore
add 41 executions against the same 35 prepared read sets, with no resimulation.

The controlled error arm's exact simulator settings remain unresolved. It is
part of the budget proposal but is not an admitted executable case. Uneven
coverage and chimeric-read cases follow after their generator contracts and
realised input statistics have been validated. They must not be represented by
quietly changing only a label. More realistic composition-associated sequencing
bias is a separate later question, not implied by the error-free GC baselines.

## Admission gates before Standard can execute

1. **Freeze whole-genome sources.** Resolve each accession version, exact URL,
   archive/member inventory, licence/attribution and sequence SHA256. Record
   original and canonical FASTA hashes, topology, chromosome/plasmid type,
   lengths, ambiguous bases and recomputed GC. Reject truncated, extra or missing
   replicons. WCFS1 needs an explicit corrected-chromosome/native-plasmid set.
2. **Implement the missing simulator contracts.** Whole-genome and multi-replicon
   preparation, per-replicon coverage budgets, circular-read treatment for tiny
   plasmids, controlled errors and deterministic read-order transforms need
   tests. Freeze their definitions and verify actual reads against the truth
   inventory. Current Quick's one-fragment preparation must not admit these
   candidates by accident.
3. **Measure structure separately.** Preserve the fixed longest-single-alignment
   completion endpoint, measured identity/indels and uncapped contiguity. Add
   validated extra/duplicated sequence, circularisation/junction and structural
   correctness measurements before making repeat/structure or complete-plasmid
   claims. A 99% longest alignment alone is insufficient. An unimplemented metric
   stays null, never pass.
4. **Freeze the plan and resource contract.** Unique slots, fixed seeds, input
   hashes, assembler/version identities, commands and limits must be explicit.
   Never tune parameters or replace a failure after observing the panel. A new
   version receives a new ID and the same frozen inputs.
5. **Prove the orchestration on small cases first.** Exercise online/offline
   preparation, failure accounting, resume without duplicate assemblies, complete
   exports and cleanup guards. Exported software failures remain outcomes;
   infrastructure/assessment errors block a completed scientific release.

The next implementation step is the reference-admission and multi-replicon
generator layer, followed by the small-plasmid/structural assessment checks.
Do not enable `--preset standard` merely because this proposal JSON exists.
