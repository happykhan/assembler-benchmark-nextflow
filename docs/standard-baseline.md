# Small simulated Standard baseline

This first Standard slice validates whole-genome execution. It contains the
whole published *Bacillus subtilis* 168 and original *Lactococcus lactis* IL1403
chromosomes, whose exact source bytes and inventories have passed reference
admission. It is **baseline validation, excluded from headline rankings**.
It does not admit the larger proposed panel or any real-read dataset.

Each reference has one case: error-free, uniformly sampled Badread reads at
30×, length distribution centred on 10 kb with 2 kb standard deviation, seed 42.
Both selected assembler versions receive identical reads within each case.
The default two versions therefore give four expected execution/assessment
slots. The cases sit in `gc-composition` for descriptive comparison; two
different species cannot establish that GC caused an assembly difference.

Standard requests four CPUs, 16 GB and four hours for each assembly. Simulation
requests one CPU and two hours. These are declared workload limits, not measured
resource use. Quick retains its smaller development resource policy.

```bash
python3 bin/plan.py --preset standard --out standard-plan.json
pixi run --locked --manifest-path environments/pixi.toml python bin/launch.py \
  --run-id standard-baseline-001 --preset standard \
  --outdir results/standard-baseline-001 --work-dir work/standard-baseline-001 \
  -- -profile bmrc,pixi --offline
```

Prepare references on a networked host first when using `--offline`; each cache
entry is revalidated against its admitted archive and molecule hashes. Unknown,
proposed, truncated or Quick-fragment references cannot become Standard inputs.
Plans bind the selected manifest, versioned assembler definitions, admission
receipts, source hashes, resources and exact expected slots before scheduling.

Plasmid-depth contrasts, native repeats, controlled errors, read-order changes
and a broader GC panel remain separate admission work. Structural correctness
remains unmeasured until its assessor is implemented and validated. Whole-genome
completion is the existing longest-alignment endpoint; it is not a proof of
biological reference correctness or suitability as truth for later real reads.

## Verified first run

`standard-baseline-v1` completed all four execution/assessment slots. Its two
exact 30× datasets passed a full read-to-source audit: 197,435,850 bases and 19,784
reads, with no mismatches. All four assemblies were incomplete under the fixed
completion criterion; their outcomes remain recorded without reruns or tuning.

The workflow passed 85 tests and an export-only resume check: all 13 compute tasks
were cached while the report was regenerated. See
[verification](verification.md#admitted-whole-genome-standard-baseline) for scope,
retention, hashes and the audit source.
