# Add an assembler or version

Every admitted definition has an immutable ID such as `flye-2.9.6`. Short aliases
are resolved when a plan is frozen; results always retain the immutable ID.
Definitions never contain arbitrary shell commands.

## A new version of an existing adapter

1. Add a Pixi feature with an exact package pin and a distinct named environment
   in `environments/pixi.toml`. Keep earlier environments and definitions.
2. Add the new `tool-version` definition in `assets/assemblers.json`, pointing at
   that environment and its tested adapter. A convenience alias may point to the
   new version, but existing frozen plans remain unchanged.
3. Resolve and commit the updated lock. Run the contract tests, then inspect a
   plan selecting the exact new ID with `bin/plan.py`. Validate a small actual
   Quick run in the new environment before treating the version as admitted.

No Nextflow process or assembler command function needs to change when an
existing adapter supports the new version's interface. If the interface changed,
add and test a separate adapter rather than silently changing earlier behaviour.

## A different assembler

Add a small adapter in `benchlib/adapters.py` declaring the executable, package,
argv builder and expected final FASTA/optional graph paths. Register it in
`ADAPTERS`, add the pinned environment and immutable declaration, and test both
successful outputs and genuine failures. The workflow handles fan-out,
assessment, retention and export without tool-specific branching.

Versions are checked at execution time. Missing environments, loose version
pins, unknown IDs and unsupported adapters are rejected. Each execution records
its definition, environment, actual version, commands and source/lock hashes.

## Runtime and plan boundaries

The verified initial runtime is Linux Pixi. Each assembler stage selects its
own named environment; simulation, assessment and export use the tooling
environment. The current container profiles use a shared digest-pinned Pixi
runtime and the same locked named environments. The per-definition `container`
field is reserved for future self-contained tool images; `null` does not prevent
using the shared runtime. See [runtime verification](native-entry-verification.md).

Changes to registry/reference/case metadata or environment locks require a new
frozen plan. Use a new run ID and output/work directories for changed selections.
To resume an earlier frozen definition after further development, use its
original checkout and lock rather than rewriting its plan or results.
