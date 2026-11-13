# Reference records and shared cache

`assets/references.json` retains admitted reference records and source attribution.
The common `assets/catalogue.json` selects datasets and their dependencies.
Runtime data are stored under the explicit `--cache_dir`, with source archives
in `references/archives/` and canonical shared references in `references/prepared/`.
Owned-work cleanup never deletes this scientific cache.
