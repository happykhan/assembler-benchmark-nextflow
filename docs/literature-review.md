# Literature informing the isolate long-read benchmark

Reviewed 11 November 2026. This is a targeted design review of primary papers,
their code and data documentation, rather than a systematic review or a new
assembler ranking. No datasets have been admitted or run as part of this review.

## Scope

The benchmark is for **single-isolate bacterial long-read assembly**. Simulated
data come first; real isolate data follow after the simulated workflow works.
There will be **no metagenomic or hybrid benchmarking track**. A paper containing
those comparison arms can still inform software design or reference validation,
but its out-of-scope arms and results do not enter this benchmark. Short reads
used by a study to validate its reference do not make our tested assembly
workflow a hybrid workflow.

## What already exists

| Work and date | What was done | What transfers, and limits |
| --- | --- | --- |
| [Wick and Holt, long-read assembler comparison](https://pmc.ncbi.nlm.nih.gov/articles/PMC6966772/); first published 23 December 2019, version 4 published 1 February 2021 | Eight assembler workflows, 500 simulated and 120 real read sets; assessed structural completeness, sequence identity, circularisation and resources. Published scripts, reads, references, commands and results. | The closest scientific predecessor: retain separate chromosome/plasmid outcomes and explicit assembler-plus-polisher definitions. Its data and software predate contemporary ONT chemistry; old rankings are not current rankings. |
| [Wick/Holt supplementary repository](https://github.com/rrwick/Long-read-assembler-comparison) | Simulation varied depth, length, identity and read artefacts; assessed plasmid size/depth and clean circularisation. Completion used contiguity of at least 99%. | Reuse a documented, versioned assessment definition rather than silently replacing it with N50. Our fixed-base bimodal experiment is a controlled extension; this review did not establish that exact experiment as already published there. |
| [Johnson et al., small plasmids](https://pmc.ncbi.nlm.nih.gov/articles/PMC10272865/), 24 May 2023 | Replicate assemblies of isolate read subsets; examined recovery by plasmid size and distinguished misplaced or duplicated plasmid sequence. ONT data used R9.4.1 and Rapid Barcoding Kit SQK-RBKP004. | Retain size-stratified plasmid outcomes, duplication and chromosome-incorporation checks. Their >90% summed-alignment recovery definition differs from our longest-single-alignment 99% endpoint and must not be pooled with it. Hybrid comparison arms are excluded here. |
| [Hybracter](https://doi.org/10.1099/mgen.0.001244), 8 May 2024, and [benchmark repository](https://github.com/gbouras13/hybracter_benchmarking) | Automated assembly/polishing; benchmarked 30 isolates and published reference material, dependency versions and replication code. The repository separates chromosome/plasmid references and includes depth analyses. | Inspect the **long-read-only** arm and evidence retention. It shows that whole workflows, not just assembler binaries, need explicit identities. Reference provenance and supplementary plasmid evidence require inspection; hybrid results are outside our scope. |
| [Sanderson et al., R10.4.1 reconstruction accuracy](https://doi.org/10.1099/mgen.0.001246), 7 May 2024 | Thirteen isolates, R10.4.1/kit14, updated bacterial basecallers, comparisons with corrected reference genomes and depth evaluation. | Useful modern-chemistry real-isolate candidate source. Record kit, basecaller/model and reference construction separately; depth findings from this small panel are not universal admission thresholds. |
| [Abdel-Glil et al., reproducibility](https://pmc.ncbi.nlm.nih.gov/articles/PMC11927881/), 21 March 2025 | Five reference strains, eight technical sequencing replicates, automated nanobacta workflow; measured sequence discrepancies and plasmid recovery. R10.4.1 sequencing; basecalled data are under PRJNA1206708. | Distinguish sequencing-replicate variation from repeated execution on identical bytes and from read-order variation. Reference agreement and output-to-output agreement answer different questions. Only long-read-only assembly arms are relevant. |
| [Autocycler](https://doi.org/10.1093/bioinformatics/btaf474), advance publication 28 August 2025 | Five isolates with six non-overlapping 50× read subsets each; modern ONT Rapid V14 and Dorado v0.9.5/sup@v5.0.0. Evaluated base errors, missing/extra sequence and resources against carefully constructed references. | A strong modern design comparator: separate base accuracy from structural error, retain subset identities and count complete workflows. Its mixed-genome experiment and metagenomic-capable comparison tools do not expand our scope. |
| [Wick's version update](https://rrwick.github.io/2025/09/23/autocycler-benchmark-update.html), 23 September 2025 | The author reran newly released assembler versions through the same benchmark pipeline used for the Autocycler paper. | Direct precedent for immutable version definitions and comparable reruns. Treat the post as an author-maintained update, distinct from the peer-reviewed paper. Do not silently replace an older version's results. |
| [Nagy et al., 92-isolate evaluation](https://doi.org/10.1099/mgen.0.001631), 27 February 2026 | Clinical Enterobacterales, R10.4.1 and SUP basecalling reported as Dorado v5.0.0; compared long-read-only assemblers/polishers as well as out-of-scope hybrid arms, including plasmid reconstruction. | The paper explicitly notes uncertainty in plasmid ground truth. Audit executable versus model version before admission. Its taxonomic concentration limits generalisation to GC extremes; publication date is not sequencing date. |
| [LORA](https://doi.org/10.1093/nargab/lqag062), 23 June 2026 | A Snakemake multi-assembler long-read pipeline with local/cluster execution, quality assessment and interactive HTML; demonstrations include bacterial and unicellular eukaryotic datasets. | Multi-assembler orchestration and standalone reports already exist. Our added purpose is a frozen, selectable **controlled benchmark**, with auditable failure accounting and cleanup. Eukaryotic and mixed samples stay excluded. |

## The two user-supplied precedents

The [nucleotid.es about page](http://nucleotid.es/about/) timed out during this
review, so its current availability or maintenance status is unverified. Its
historical design is documented by the primary
[Bioboxes paper](https://doi.org/10.1186/s13742-015-0087-0) (2015) and a
[JGI meeting abstract](https://usermeeting.jgi.doe.gov/wp-content/uploads/sites/2/2014/01/032315_UMX-Abstract-Book_ONLINE.pdf)
(2015): interchangeable container interfaces, community-submitted tools and
repeatable benchmarking against shared data. We should reuse that interface
principle: a new version declares accepted inputs, command, environment and
outputs, and passes the same contract checks. This does not establish a current
nucleotid.es bacterial long-read panel that we can simply adopt.

[PMID 36576131 / LMAS](https://doi.org/10.1093/gigascience/giac122) was published
online **28 December 2022**, in the 2023 volume of GigaScience. It benchmarks
**short-read metagenomic assembly** and is outside our scientific scope. Its
[development documentation](https://lmas.readthedocs.io/en/latest/dev/general.html)
is useful engineering precedent: Nextflow DSL2 modules for preparation,
parallel assembly, assessment and reporting, with workflow/report source split
and configurable resources. We borrow those boundaries; we do not import its
community datasets, assembler roster or scientific rankings.

## GC and simulation realism

[Delahaye and Nicolas](https://doi.org/10.1371/journal.pone.0257521), published
1 October 2021, measured composition- and motif-associated errors in bacterial
ONT reads. The relevant experiment used **R9.4.1** and **Guppy 3.3.3/4.2.2**;
its numerical error rates cannot be presented as predictions for R10.4.1/Dorado.
It nevertheless supports keeping two questions separate: an assembler's response
to genome composition under controlled reads, and its response to real
composition-associated sequencing errors or coverage effects.

A [May 2026 simulator-comparison preprint](https://doi.org/10.64898/2026.05.06.723380)
and its [author repository](https://github.com/mtaouk/ONT-Read-Simulator-Benchmarking)
compare six simulators against contemporary R10.4.1 reads. The abstract reports
that no simulator reproduces all measured properties, including context-dependent
errors. Full bioRxiv text was access-blocked in this review, so this is an
abstract-level, non-peer-reviewed warning rather than grounds to replace our
simulator. Badread's version and settings must be explicit; error-free Quick
reads are a workflow fixture, not evidence of realistic ONT performance.

## Decisions for this repository

These are design recommendations from the review, not findings produced by our
new benchmark.

1. **Finish Quick first.** Exercise reference download/checksum, simulation,
   actual assembly, assessment, failure reporting, export, resume and offline
   preparation. Label every Quick record as a workflow check and exclude it from
   headline scientific comparisons.
2. **Curate Standard as a separate frozen release.** Cover the agreed groups:
   plasmids, GC/composition, repeats/structure, read quality/sampling and
   reproducibility. Version the panel independently of assembler versions.
   Use paired controls and repeat sampling where it answers the scenario's
   question; avoid a huge uninterpretable Cartesian product.
3. **Make the bimodal experiment identifiable.** Hold total sequenced bases
   constant as agreed, report both base and read-count proportions, retain the
   realised length distribution and shuffle with a recorded seed. Separate
   length-mixture, coverage and error changes so their effects can be assessed.
4. **Keep measurements independent.** Report replicon completeness,
   circularisation/extra sequence, structural correctness, identity/indels,
   runtime and process-tree RAM separately. A long alignment or large N50 does
   not prove structural correctness. Software, infrastructure and assessment
   failures retain their own states; none implies sequence absence.
5. **Separate three reproducibility axes.** Identical input and repeated
   execution; identical read multiset with changed order; independently sampled
   reads. Real sequencing technical replicates are a fourth, later axis.
6. **Freeze fair comparisons.** All selected assemblers receive identical
   checksummed inputs for a case/repeat. Record complete commands, versions,
   polishing stages, reference/reads hashes, limits and resource scope. Preserve
   previous attempts; never silently tune a failed case or replace old results.

## Candidate real-data sources for later admission

| Candidate | Why inspect it | Still required before admission |
| --- | --- | --- |
| [Wick/Holt published reads and references](https://pmc.ncbi.nlm.nih.gov/articles/PMC6966772/) | Existing paired real inputs/reference archive and historical continuity. | Per-isolate chemistry and reference provenance; complete replicon inventory; explicit historical-chemistry stratum. |
| [Hybracter benchmark archives](https://github.com/gbouras13/hybracter_benchmarking) | Public input instructions, diverse isolate references and chromosome/plasmid material. | Resolve source versions, added plasmid evidence, licences, exact archive members and checksums; exclude hybrid test arms. |
| [Autocycler supplementary data](https://doi.org/10.1093/bioinformatics/btaf474) | Modern read chemistry with independently identified subsets and documented reference construction. | Verify downloaded files, sample matching, all replicons and per-reference confidence; do not assume published truth is infallible. |
| [nanobacta study / PRJNA1206708](https://pmc.ncbi.nlm.nih.gov/articles/PMC11927881/) | Technical replication can support a later real-data reproducibility group. | Audit isolate/run mapping, reference confidence, chemistry/model and accessible read metadata. |

No candidate is yet a validated Standard-panel member. A low/high-GC label
alone is insufficient: selection must also account for genome size, repeats,
replicon inventory, library preparation and reference confidence. This review
does not establish an exhaustive or balanced modern GC panel.
