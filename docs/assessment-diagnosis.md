# Why the four Standard assemblies were labelled incomplete

Checked against the saved `standard-baseline-v1` outputs on 11 November 2026.
No reads or assemblies were regenerated, and the original PAFs and scores were
not changed.

**The assessment arithmetic is correct for its declared endpoint. The saved
assemblies are fragmented, and “incomplete” means below 99% in one longest
alignment—not that only that fraction of the genome appears anywhere in the
assembly.** Independent checks recover more than 99% of the reference across
the contigs in every case. Fragmentation and some structural/base discrepancies
are genuine properties of the saved outputs.

| Reference | Assembler | Contigs | Longest contig / longest alignment | Reference in that alignment | Reference bases covered across contigs |
| --- | --- | ---: | ---: | ---: | ---: |
| *B. subtilis* 168 | Flye 2.9.6 | 13 | 1,365,843 bp | 32.399683% | 99.542628% |
| *B. subtilis* 168 | Raven 1.8.3 | 2 | 4,148,777 bp | 98.414724% | 99.999905% |
| *L. lactis* IL1403 | Flye 2.9.6 | 4 | 983,425 bp | 41.572099% | 99.844183% |
| *L. lactis* IL1403 | Raven 1.8.3 | 3 | 996,606 bp | 42.129296% | 99.962969% |

The final column is a separate diagnostic: union of reference positions aligned
to query bases by independent NUCmer alignments. Positions opposite query gaps
are excluded. It is not substituted into the frozen single-alignment verdict.
Coverage does not establish correct structure or perfect base accuracy.

## Independent checks

1. **Direct sequence placement.** A standalone script searches both contig
   orientations against the doubled native circular reference using exact string
   matching. It does not use minimap2, PAF parsing or the pipeline assessor. Every
   *L. lactis* contig has exactly one full-length exact placement. Its coverage
   agrees exactly with NUCmer, including 3,686 uncovered positions for Flye and
   876 for Raven. Remaining *B. subtilis* contigs required gapped alignment.
2. **Different aligner and parser.** NUCmer 4.0.0rc1 aligned all four saved outputs
   using both single-copy references with unique-reference anchors and doubled
   references with maximum matches. Best-query Delta filtering was applied.
   Both representations give identical whole-reference coverage. A separate
   Delta parser excludes query-gap positions and checks coordinate consumption
   against every alignment endpoint.
3. **Longest-alignment replication.** Doubled-reference NUCmer independently
   gives exactly the same four longest spans as the current assessment. A
   single-copy reference cuts the origin-spanning *B. subtilis* Raven alignment
   to 96.081702%; doubling restores the correct 98.414724%. The existing tripled
   reference therefore prevents an origin artefact rather than causing one.
4. **Input identity.** The preceding whole-input audit verified all 19,784 reads
   against their declared source fragments, including circular wraps and final
   budget trimming. Error-free input is established; it does not imply an
   assembler must emit one closed chromosome.

The independent alignment job was Slurm `35273660`, completed exit `0:0` in
26 seconds with one allocated CPU and approximately 278 MB maximum RSS. It used
an isolated cached MUMmer environment and did not change the project's lock or
the original benchmark artefacts.

## Important limits of the original summary

- The 99% endpoint measures contiguity of one alignment. It should be presented
  alongside whole-reference coverage and contig count so that fragmentation is
  not read as wholesale loss of sequence.
- The reported identity of 1.0 applies only to the selected longest alignment.
  It is not a whole-assembly accuracy result. For example, *B. subtilis* Flye
  `contig_7` has two large reference skips of 80,545 and 70,354 bp in the saved
  PAF, and its longest exact contig is a different record. Some skipped reference
  segments occur in other contigs. Raven's secondary *B. subtilis* contig also
  has split/gapped placements. These are not established biological deletions.
- Independent best-query alignments leave 19,281 reference positions uncovered
  for *B. subtilis* Flye and four for Raven. These are alignment-defined coverage
  gaps, separate from the much lower single-contig fractions.
- This audit establishes output fragmentation and verifies assessment geometry.
  It does not experimentally establish why either assembler chose those paths.
  Read length, repeat resolution and overlap heuristics require their own
  evidence; settings should not be tuned retrospectively to erase these results.

## Retained evidence

- `evidence/assessment-diagnosis/exact_placement.py` and `exact-placement.json`:
  direct circular placements, interval unions, contig lengths and source hashes.
- `anchor_placement.py` and `anchor-placement.json`: diagnostic exact anchors for
  the two non-exact *B. subtilis* contigs; its exact-only coverage is a lower
  bound and is not used in the table above.
- `mummer_check.py`, `mummer_check.sh` and `mummer/`: pinned tool version, commands,
  source/output hashes, original Delta alignments and coordinate tables.
- `mummer_covered_bases.py` and `mummer-covered-bases.json`: gap-aware coverage,
  uncovered intervals and matching results for both reference representations.

Large doubled FASTA working files stay on the cluster; they are not added to the
repository. All diagnostic files are separate from the frozen baseline outputs.
