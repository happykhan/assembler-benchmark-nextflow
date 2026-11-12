# Beta Standard

The beta is an executable development panel, separate from the full protocol-v1
scientific release. On 12 November the user authorised running this beta and
publishing its results on the website, keeping provenance work lightweight.

```bash
nextflow run happykhan/assembler-benchmark-nextflow --preset standard \
  -profile bmrc,pixi --outdir results/beta-standard --run_id beta-standard-v1
```

No separate preparation commands are required. References are downloaded by the
workflow, or reused from `--reference_dir` with `--offline`. Use `--groups` and
`--cases` to select a smaller slice. Baselines have multiple scenario memberships
and are executed once when groups overlap.

| Component | Inputs | Default Flye + Raven outcomes |
| --- | ---: | ---: |
| Five native reference genomes × five seeds | 25 | 50 |
| B. subtilis: 10×, shorter and bimodal reads × five seeds | 15 | 30 |
| B. subtilis: longer reads × five seeds | 5 | 10 |
| WCFS1: 0.25× and 4× relative plasmid depth × five seeds | 10 | 20 |
| Total | **55** | **110** |

Seeds are 101, 202, 303, 404 and 505. References are B. subtilis 168,
L. lactis IL1403, M. florum L1 (27.02% GC), M. luteus NCTC 2665 (73.00% GC)
and L. plantarum WCFS1 with its three native plasmids. Existing read-order
diagnostics remain independently selectable through `--track diagnostic --groups S7`.
Additional Standard execution repeats/order transforms are not in this beta's
110 outcomes. Error and bias scenarios remain deferred.

The new `native-error-free-v1` sampler implements exact per-molecule base budgets,
uniform circular starts and gamma lengths. Fragments never exceed one native
molecule length. Headers record source accession, start, length, strand and mode.
Quality scores are synthetic Q40. This beta simulation is a new method; earlier
Badread baseline results remain historical development observations.

Baseline depth is 30×; single long-mode mean/SD is 10,000/2,000 bp. Short reads use
2,000/400 bp; the bimodal arm allocates half its bases to 1,000/250 bp and half
to 10,000/2,000 bp. The long arm uses 20,000/4,000 bp. Plasmid-depth arms hold the
chromosome at 30× and assign plasmids 7.5× or 120×. The 10× single-chromosome arm
is a base-budget prefix of its 30× baseline. Actual lengths, counts, base/read
fractions and per-molecule coverage are saved.

GC comparisons are descriptive across different species. The longer-read arm
does not establish repeat resolution or structural correctness. Completion uses
the existing 99% longest-alignment endpoint with uncapped contiguity. There is no
overall winner score, and beta results are excluded from historical denominators.

## Website publication

After the actual run completes, the compact report can be added to a copy of the
current website without replacing the general table or historical scenarios:

```bash
python3 bin/build-beta-site.py --bundle results/beta-standard/bundle \
  --base-site /path/to/current/site --out-dir .cache/beta-publication
```

This is an internal publication command, not a prerequisite for running Nextflow.
It adds `/beta/`, run and molecule TSVs, a figure and filters, plus a homepage link.
The existing pages are preserved. The normal site size/link checks apply. A beta
is not labelled live until the deployed report and downloads have been checked.
