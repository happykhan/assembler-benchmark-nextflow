# Why the error-free baseline is not chromosome-contiguous

Reviewed 11 November 2026 against the four saved Standard outputs. No reads,
assemblies, parameters or original measurements were changed. This review
separates an observed assembly result from hypotheses about its cause.

## What the retained outputs establish

The saved FASTAs are fragmented before assessment: Flye has 13 *B. subtilis*
contigs and four *L. lactis* contigs; Raven has two and three respectively.
The final Flye Lactococcus graph has four segments and no links. Its four
`assembly_info.txt` records are non-circular, single-copy, non-repetitive contigs.
The Bacillus Flye graph has 13 segments and two links; its final contigs are also
marked non-circular. These graph records establish output topology, not the
biological reason for each break.

The [independent assessment diagnosis](assessment-diagnosis.md) checks sequence
placement and the longest-alignment endpoint separately. Bacillus includes
non-exact structural joins as well as fragmented output, so **fragmentation
alone is not a complete description of every saved assembly**.

## The inputs contain the missing Lactococcus regions

The earlier full-input audit verified all 19,784 reads against their declared
strand-specific native circular source fragments. A separate read-coordinate
audit confirms that every reference base is covered by at least one realised
read in both datasets. Nominal mean depth is exactly 30×, but depth is not
uniform at every individual position.

The three Lactococcus gaps independently identified by exact contig placement
are spanned by existing reads:

| Output | Gap, zero-based half-open | Gap length | Reads spanning gap | Reads spanning gap plus 1 kb on each side |
| --- | --- | ---: | ---: | ---: |
| Flye | 537339–538743 | 1,404 bp | 22 | 17 |
| Flye | 1984040–1986322 | 2,282 bp | 17 | 14 |
| Raven | 452960–453836 | 876 bp | 36 | 24 |

These are geometric source-coordinate counts. The flanks have not been proved
unique, and the counts do not reproduce an assembler's filtering or establish
repeat resolvability. They do rule out the simple explanation that these
sequence regions were absent from the simulated reads.

## Workflow configuration matters

The saved Flye command explicitly uses `--nano-raw`; there was no automatic
selection of a high-quality/corrected input mode. The
[version 2.9.6 manual](https://github.com/mikolmogorov/Flye/blob/2.9.6/docs/USAGE.md)
associates that mode with older, noisier ONT data and provides separate
high-quality and corrected-read modes. It also explains that automatic overlap
selection uses the length distribution and that stringent overlap requirements
can create gaps. This makes input-mode choice a benchmark-design concern for
perfect simulated reads. It does **not** demonstrate that changing a flag would
resolve these particular outputs or explain Raven's results.

Both Flye logs selected an 8,000 bp minimum overlap. Read N50 was approximately
10.2 kb and N90 approximately 7.87 kb; observed overlap-based coverage was 20
for Bacillus and 23 for Lactococcus. The logged non-zero overlap divergences
are internal approximate-overlap measurements, not evidence of input read
errors: the independent byte comparison found none.

An additional exact-coordinate model asks how reads would connect if every
join strictly required an 8 kb physical overlap. Its transformed intervals
`[start,end−8000]` have mean depth 6.37× in Bacillus and 6.35× in Lactococcus,
leaving 20 and nine circular gaps respectively. This model deliberately omits
repeat overlaps, approximate alignment and internal graph heuristics. Its gaps
do not explain all exported contig breaks, so it is **supporting geometry, not
a causal replay of Flye**.

[Raven's versioned documentation](https://github.com/lbcb-sci/raven/blob/1.8.3/README.md)
describes a long-uncorrected-read assembler with overlap filtering, a default
minimum unitig size and two polishing rounds. Our saved invocation uses its
defaults apart from threads and GFA output. Polishing logs report overlap counts
equal to the respective input read counts. These aggregate counts do not prove
individual read assignments or establish which graph decision caused each break.

## Bounded conclusion

The present evidence supports actual fragmented/structurally imperfect saved
assemblies and a strict single-alignment completion endpoint; it does not support
discarding the observations as a scoring failure. Error-free bases remove one
source of difficulty, but do not guarantee every assembly connection will be
resolved under a fixed workflow. The exact causal contributions of repeats,
overlap heuristics and input-mode choice remain unresolved without a separately
declared controlled experiment. No such rerun or tuning was performed here.

Read-only evidence and the two small Slurm audit jobs are retained under
[`evidence/fragmentation-review`](../evidence/fragmentation-review/). Source
commands, graph summaries, input hashes, coordinate counts and audit program
hashes are included there.
