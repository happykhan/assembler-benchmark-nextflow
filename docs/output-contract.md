# Current-result output contract

Schema version 2 separates scientific identity from operational attempts. One
current result identifies a case, stable assembler configuration and optional
scientific repeat. The common catalogue supplies the `result-<24 hex>` identity:
SHA256 of compact JSON `[case_id, workflow_id, scientific_repeat_id]`. Workflow
versions are outside that identity. The separate case `science_key` prevents
silently replacing a different scientific experiment. Membership changes do not
duplicate inputs or executions.

Records explicitly describe short/long technology, real/simulated source,
experiment, input, configuration and actual software version. Every metric has a
name, value, method and unit. Null means unmeasured. Statuses remain distinct:
`measured`, `execution_failure`, `assessment_failure`, `not_applicable`, `not_run`.
Failure cannot establish a top-level sequence outcome.

```text
results/
  catalogue.json
  packages/<result_id>/<current-generation>/
    result.json
    measurements.tsv
    index.html
    manifest.json
    artifacts/...
  dependencies/<shared-id>/dependency.json, manifest.json, shared files...
  summaries/collection/<id>/summary.json, measurements.tsv, index.html...
  summaries/scenario/<id>/summary.json, measurements.tsv, index.html...
```

The root catalogue is the atomic commit point. Each referenced package is fully
written and validated before an atomic catalogue replacement makes it current.
The previous owned package is then removed, including old successful artifacts
when a replacement fails. Unrelated results remain intact. Generation names are
storage details, not an exposed result history. Per-result and per-dependency
atomic directory locks permit independent staging; a short catalogue lock commits
updates. Uncertain locks are never stolen. Readers/exporters take the catalogue
lock for consistent snapshots. This guarantees atomic visibility, not durability
across storage power loss.

Actual software version and explicit integer `version_order` must agree. Lower
orders cannot replace newer versions; conflicting versions/orders are rejected.
A version upgrade preserves the stable configuration; changing configuration
parameters needs a new configuration ID. Same-version reruns replace current,
including failures. Scientific repeats retain separate deliberate repeat IDs and matching descriptions with a kind and positive index. Unrun and inapplicable records cannot contain measured values.

Case packages include readable HTML, JSON and TSV, input/experiment descriptions,
configuration, methods, units and supporting artifacts. Sources are API transport
arguments, never serialized absolute work paths. Artifact paths are relative.
Shared references and input resources live once under immutable dependency IDs;
conflicting bytes or metadata for an existing ID are rejected. Summaries reference
shared case packages instead of copying assemblies.

`publish_result` immediately publishes one standalone case result without an
all-results barrier or website build. It invalidates affected summaries so stale
success displays do not survive a failure replacement. `refresh_summaries` is an
optional separate aggregation step. `set_catalogue_metadata` updates collection
and scenario definitions without dropping current results.

`export_subset` copies selected cases and their dependency closure once, with
regular files/directories and package-relative links. The copy needs neither the
original Nextflow work directories nor the hosted site, and can itself receive
scoped result replacements.

```python
publish_result(root, record, artifacts={"assembly.fasta": source_path},
    dependencies={"reference-id": {"record": {"kind": "reference"},
        "files": {"reference.fasta": reference_path}}})
set_catalogue_metadata(root, {"collections": definitions, "scenarios": scenarios})
records = load_current(root, with_packages=True)
refresh_summaries(root)  # optional, no sequence analysis
export_subset(root, new_directory, result_ids=selected_ids)
validate_package(case_package)
```

`load_current(..., with_packages=True)` adds the root-relative package location.
Full artifact verification is the default; metadata-only readers can explicitly
set `verify_artifacts=False`. Shared presentation helpers are `render_page` and
`render_metric_table`. Public website builds consume only compact records and
prepared visual artifacts; raw scientific outputs remain in standalone packages.


Aggregation also writes `selection.json` for the latest selected workload:
expected, available and missing stable result IDs, status counts and separate
slot/assessment completeness flags. A recorded execution failure can complete a
slot; an assessment failure does not complete its sequence measurement. These
flags do not turn incomplete genomes into complete genomes. Unrelated current
results remain indexed and are excluded from selected-slot counts.

Published input descriptions retain source archive identity, declared local
filenames or public URLs, sample/reference binding and attribution without
requiring original host paths. The assessment verifies the retained execution's
exact prepared-input binding before mapping.
