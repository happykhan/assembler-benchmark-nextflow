# Current-result reporting

`current_site.py` builds a portable static website from the current-result catalogue. It reads stored measurements and prepared visual artefacts; it never runs assemblers or recomputes scientific assessments.

```bash
python3 bin/render-current.py --results results --outdir site
```

The results store is the primary output. Website generation is optional and reads whatever current results are available. Broad benchmark collections and targeted scenarios reference the same result packages. Pages show the scientific question, conditions, typed filters, separate scientific and resource measurements, and links to result details.

The public site contains compact JSON, TSV, prepared graphs and alignment plots. Reads, raw logs, large sequence files and workflow work directories remain outside the public copy. Its links are relative, so it can be copied without the workflow checkout or original results store.

The standalone scientific packages, replacement rules and subset exports are documented in [the output contract](../docs/output-contract.md). Presentation assets are in `current_assets/`; the established typeface and light/dark colour system are retained.

Validation:

```bash
python3 -m unittest tests.test_current_results tests.test_current_site
node tests/browser/validate-current-site.mjs site browser-qa
```

The browser check requires Playwright and Chromium; set `PLAYWRIGHT_MODULE_PATH` and `CHROMIUM_EXECUTABLE` when they are not installed in the default locations.
