# Add an assembler or update its version

`assets/catalogue.json` is the single workflow catalogue. Each stable workflow
ID represents a tested scientific configuration (for example `raven-default`),
with explicit supported read technologies, source kinds and case eligibility.
Its current result stores the actual software version.

For a new version, update that workflow's version and monotonic `version_order`,
add its exact Pixi package pin and named environment, then regenerate and commit
the lock. Do not change the stable ID merely to retain operational history.
The current-result store rejects downgrades and changes to the tool or scientific
configuration under an existing ID. A different configuration needs its own ID.
Existing scientific repeats retain their separate identities.

For a new tool, add a tested argv-based adapter in `benchlib/adapters.py`, declare
its final FASTA and optional graph, then add the workflow and software dependency
to the catalogue. Declare supported options in `benchlib/workflow_options.py`;
new input layouts or compound outputs need an explicitly tested typed runner. Paired-end and long-read interfaces are explicit; incompatible
case/workflow combinations become `not_applicable` without scheduling assembly.
Test both successful output and genuine failures. Never turn a failed execution
or failed measurement into a claim that a sequence is absent.

First inspect the intended small selection:

```bash
nextflow run . --cases quick-long --workflows raven-default --plan_only
nextflow run . --cases quick-long --workflows raven-default -profile bmrc,pixi -resume
```

Adding a workflow reuses unchanged prepared inputs. Updating assessment or
presentation reuses retained assemblies; only deliberate `--rerun` bypasses the
selected assembly cache. A replacement failure removes stale success artifacts.
Unrelated current results stay in the same output directory.
