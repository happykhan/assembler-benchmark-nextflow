# Current-result website validation

Validated the five actual Cluster 3 current records copied into `.cache/refactor-verification/current`: three measured results (Quick long-read Raven, Quick ART paired-end SKESA, and matched local real-input Raven) and two explicitly inapplicable technology/workflow combinations. These small checks establish workflow behaviour, not panel-level scientific performance.

- `browser-qa.json`: 12 original actual-result checks, desktop/mobile and light/dark, home/comparison/detail. All routes and downloads available, no overflow or browser errors; filters and graph controls pass.
- `actual-contact-sheet.png`: inspected montage of all 12 actual-result captures. No material visual defect identified. Mobile comparison tables scroll within the page.
- `portability.json`: all five current packages exported with dependency closure. The original result root was renamed and absent while standalone package checks, 67 relative links and website rendering ran; restored afterwards. No symlinks. The website has 45 files, 331,960 bytes, largest file 48,609 bytes, and 204 working local links. Limits: 64 MiB total, 1,500 files, 5 MiB/file.
- `portable-browser-qa.json`: the same 12 browser checks pass on the website rebuilt solely from exported packages.
- `contract-tests.txt`: 18 package/site tests pass, including scoped failure replacement, version/configuration guards, concurrent publication, portability, incremental catalogue definitions, explicit not-run status, and distinct scientific repeats in tables/downloads. Synthetic fixtures are used for failure/unrun/repeat paths; these are software checks, not fabricated measured outcomes.

Public rendering only consumes stored measurements and prepared graph/alignment assets. Large reads, assemblies, raw graphs, mapper output and logs are excluded. Raw scientific output and historical evidence were not removed. Obsolete batch/release reporting code and old generated website assets were retired. No production deployment was made by this validation.

## Final mixed snapshot

The final atomic cluster snapshot was pulled fresh into `.cache/refactor-verification/final-snapshot`; the separate failed earlier `final-current` copy was not used. `final-snapshot.json` verifies all 18 current entries: seven measured, eleven inapplicable, three measured inputs, one real measured result and three distinct technical repeat identities. A second standalone export was validated and rendered with its original snapshot root temporarily unavailable, checking 187 package-relative links.

`final-browser-qa.json` passes all 12 standard desktop/mobile light/dark checks. `final-extra-browser-qa.json` passes 16 more checks across broad reproducibility, targeted reproducibility, plasmids and the actual real-input detail page. All three repeat labels and real-source labels are present; downloads resolve, with no overflow or browser errors. `final-contact-sheet.png` records inspected representative final captures.

The copied final public website contains 103 files and 598,086 bytes including its 304-byte ownership/validation marker; pre-marker rendering reported 102 files and 597,782 bytes. Largest public file: 51,537 bytes. All 452 local links resolve. These remain validation outputs; no production deployment is claimed.
