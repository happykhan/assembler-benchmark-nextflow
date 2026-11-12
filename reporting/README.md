# Standalone result archives and website

`reporting` replaces the historical presentation backend. It contains no Slurm
controller, job submission, polling or assembler invocation. The presentation
code was extracted from the frozen Ploptimizer report implementation; historical
scientific method labels and attribution remain intact.

```
python3 bin/import-results.py --source /path/to/sealed-bundle --out-dir results/imported
python3 bin/render-website.py --bundle results/imported --out-dir results/website
```

Admission verifies all SHA-256 bindings and producer identities, copies every
source file byte for byte and places its receipt **beside** the immutable archive.
It rejects extra files, symlinks, changed evidence, duplicated identities and
changed frozen native slots. Two producers are supported: the frozen historical
bundle and native Nextflow exports. Rendering cannot discover additional source
runs or recompute missing measurements.

Native export parses retained GFA into bounded, sequence-free interactive graph
models. It prepares figures and TSVs from source-bound saved PAF coordinates;
tripled reference coordinates remain labelled as tripled. Missing origin evidence
stays unassigned. The website consumes these sealed models and copies prepared
figures; it never aligns or evaluates sequences. Diagnostic exact-copy, general
Wick completion, supplementary paper recovery and S7 output agreement remain
separate endpoints.

Historical rendering retains all batch/result routes, S1–S7, general performance
and aggregate pages, diagnostic plots, graphs, saved coordinates and TSVs. The
complete archive remains separate from the public website. The shared release
gate checks links, graph/evidence bindings and the 64 MiB / 1,500 file / 5 MiB per
file limits. Frontend sources and verified built assets are included; regenerating
assets uses the pinned versions in `website/package.json`.

Run `python3 -m unittest discover -s tests -p 'test_*presentation.py'` and
`python3 -m unittest discover -s tests -p test_website_parity.py`. For the full
historical equivalence check, set `BENCHMARK_HISTORICAL_BUNDLE` to a frozen archive
and optionally `BENCHMARK_HISTORICAL_SITE` to the verified reference website.
The test imports evidence, prevents the renderer reading the original source,
prohibits subprocess execution and compares every public payload file hash.
