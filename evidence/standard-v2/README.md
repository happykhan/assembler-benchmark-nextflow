# Standard native simulated run, 16 November 2026

Standard was launched from source `aa7862d` after reviewing the measured pilot
packages and their saved alignments. It has 55 prepared inputs and 110 selected
outcomes (Flye 2.9.6 and Raven 1.8.3). The exact runtime plan, job trace and source
snapshot are retained under the remote root recorded in `launch.json`.

**This is launch evidence, not a completed or published Standard release.** SSH
began timing out during monitoring. The last confirmed count is an earlier
checkpoint; pending results must not be described as currently running.
Do not launch a duplicate run. Once access returns, inspect `run.exit`, the
existing controller and scoped trace job IDs before deciding whether any resume
is needed. Genuine assembler/resource failures remain outcomes.

Pilot review found no failed execution/input bindings or assessment failures.
The four Raven runs of the same Quick long-read fixture produced byte-identical
assemblies (`fadc94cd68c8ee2775796e0f5b070d897517cbfe741cd611c6f0d7210b5580df`).
The saved Flye alignment explains its low identity: a 38,311 bp deletion is
included in the selected alignment block. Error-free input therefore does not
establish a complete or correct assembly. The Quick reference is a linear
200 kb engineering fixture, and its tripled-reference alignments are unsuitable
for broad scientific recovery claims. Standard uses native circular references.
The small real-read subset and ART short-read pilot remain separate.

Before publication:

1. Require the original run to finish and verify terminal accounting for its
   scoped scheduler job IDs. Account for every selected slot and failure class.
2. Export a locked portable snapshot of all 110 current results and shared
   dependencies. Copy `selection.json` alongside it after confirming the source
   is quiescent; the generic subset exporter does not copy this run summary.
3. Run `verify_snapshot.py` against that snapshot and its frozen runtime plan.
   It verifies artifact hashes, exact case selection, versions, execution/input
   bindings and replays longest-alignment summaries from retained PAFs. It does
   not generate new alignments, reads or assemblies.
4. Render with `bin/render-current.py --standard`. This refuses an incomplete or
   unresolved selection and labels pages and exports as simulated Standard.
5. Compose using `bin/compose-standard.py` and the verified current website.
   Keep the pilot and primary published general/S5/S6/S7 artifacts unchanged.
   Supplementary `/batches/*` URLs are rewritten to the pinned archive deployment
   in `archive.json`, preserving their bytes while keeping the deployment under
   64 MiB, 1,500 files and 5 MiB per file. Never delete that archive deployment
   while a published site depends on it.
6. Verify desktop/mobile pages, figures, downloads and archived URLs before and
   after promotion. Record the actual live deployment in the release metadata.

The production website has not been changed by this launch or report preparation.
