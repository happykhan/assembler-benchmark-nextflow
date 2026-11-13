# Refactor verification

These checks validate the new catalogue, preparation, execution and current-result
contract with small inputs on Cluster 3. They do not establish full-panel assembler
performance. These refactor checks preceded the separate labelled pilot publication.
The pilot reports are now [live](https://ploptimizer-assembly-benchmark.vercel.app/pilot/),
with the existing benchmark reports preserved.

| Acceptance area | Result | Evidence and scope |
| --- | --- | --- |
| Dependency dry-run and invalid paths | Passed | [Preparation tests](../evidence/refactor-v2/preparation/preparation-tests.log): 15 tests on GPFS cover missing/invalid dependencies, interrupted transfer, corruption, subset closure and no-download inspection. [Runtime tests](../evidence/refactor-v2/preparation/runtime-tests.log): 16 checks cover missing bootstrap/runtime resources and invalid pins/receipts. |
| Shared cache across nodes | Passed | [Two-node proof](../evidence/refactor-v2/preparation/two-node-verification.json): two requesters on separate compute nodes produced one HTTP download and one verified 77,824-byte copy; two offline blocked requesters reused it. Atomic directory locks and post-lock rechecks were exercised on GPFS. |
| Pinned container preparation | Passed, limited scope | [Container verification](../evidence/refactor-v2/container/verification.json): real digest-pinned SIF acquisition, receipt/checksum verification and cached Apptainer execution. A child process inside the image was denied IPv4/IPv6 sockets. Docker daemon behaviour has contract tests; scientific Docker execution is not claimed. |
| Cold offline Quick, end to end | Passed | [Final split-entrypoint verification](../evidence/refactor-v2/offline/final-verification.json), plus the earlier [cold verification](../evidence/refactor-v2/offline/cold-verification.json) and [trace](../evidence/refactor-v2/offline/cold-trace.tsv): exit 0, all 15 tasks completed, starting without prepared scientific inputs. Two inputs were simulated and assembled: native long reads/Raven and ART paired-end reads/SKESA. Two results were measured and two combinations explicitly inapplicable. Scientific tasks ran inside the admitted SIF. |
| Outbound access blocked | Passed for task programs | [Network probes](../evidence/refactor-v2/preparation/network-child-proof.json) prove inherited seccomp denial of IPv4/IPv6 sockets while AF_UNIX remains available. The cold verification records the blocker in every task command. The Nextflow/Slurm controller remained outside the filter so it could contact the scheduler. |
| Matched real-input pilot | Passed | The copied current store used for [website validation](../evidence/refactor-v2/website/README.md) contains the completed real-input Raven result alongside two simulated measured results and two inapplicable entries. This is a small matched pilot, not a real-data panel or proof that the comparator is error-free truth. |
| Assessment change reuses assembly | Passed | [Assessment-change trace](../evidence/refactor-v2/cluster/cache-assessment.trace.tsv): both assembly tasks were cached while both assessments executed again. Prepared inputs were cached. |
| Rendering change reuses science | Passed | [Rendering-change trace](../evidence/refactor-v2/cluster/cache-render.trace.tsv): both assemblies and assessments were cached; rendering completed. |
| Adding a workflow reuses existing work | Passed | [Added-workflow trace](../evidence/refactor-v2/cluster/cache-added.trace.tsv): existing Raven/SKESA inputs, assemblies and assessments were cached; only the added compatible Flye assembly/assessment executed. Cross-technology exclusions were explicit. [Baseline trace](../evidence/refactor-v2/cluster/baseline-trace.tsv) records the starting Quick run. |
| Atomic current replacement and explicit statuses | Passed with software fixtures | [Contract/site tests](../evidence/refactor-v2/website/contract-tests.txt): 18 checks cover failure replacing success, removal of stale artifacts, unrelated records preserved, upgrades/downgrade protection, stable configuration guards, concurrency, not-run records and scientific repeats. Fixtures for failure/unrun/repeat paths are software tests, not fabricated benchmark observations. |
| Portable standalone subset and public site | Passed | [Portability proof](../evidence/refactor-v2/website/portability.json): five current packages exported with dependencies once; the original result root was absent during validation/rendering. All 67 standalone links and 204 website links resolved. Public payload: 45 files, 331,960 bytes; largest file 48,609 bytes. Limits: 64 MiB total, 1,500 files, 5 MiB/file. |
| Desktop/mobile presentation and downloads | Passed | [Actual browser checks](../evidence/refactor-v2/website/browser-qa.json) and [portable browser checks](../evidence/refactor-v2/website/portable-browser-qa.json): each passes 12 combinations of home/comparison/detail, desktop/mobile and light/dark. Filters, graph controls and downloads worked; no page errors or overflow. [Inspected captures](../evidence/refactor-v2/website/actual-contact-sheet.png). |
| Final mixed workflow selection | Passed | [Final mixed trace](../evidence/refactor-v2/cluster/final-mixed.trace.tsv) and [atomic snapshot](../evidence/refactor-v2/website/final-snapshot.json): 18 current entries, seven measured and eleven inapplicable, using three distinct measured inputs. Includes one real measured result and three explicit technical repeats. All packages validate; a second portable export works while its original root is absent, with 187 standalone links checked. [Core browser checks](../evidence/refactor-v2/website/final-browser-qa.json) pass 12/12 and [real/reproducibility/plasmid checks](../evidence/refactor-v2/website/final-extra-browser-qa.json) pass 16/16, including all three repeat labels. Final copied website: 103 files including its marker, 598,086 bytes, largest file 51,537 bytes, 452 working local links. |


A mixed-selection check exposed work-path coupling after a preparation task was
rebuilt. Preparation now has separate thin entry points for setup, admission and
scientific input generation; publication code is outside those fingerprints.
Assemblers receive the canonical immutable prepared-cache path, rather than a
transient preparation-task symlink. [Publication-only changes](../evidence/refactor-v2/cluster/cache-publication.trace.tsv)
and [preparation-wrapper repairs](../evidence/refactor-v2/cluster/cache-input-wrapper.trace.tsv)
were then exercised: both assemblies and both assessments stayed cached, including
when preparation tasks executed again. Reference registry metadata also
participates in planning's cache dependency.

[Final binding/accounting verification](../evidence/refactor-v2/cluster/final-acceptance.json)
checks all seven measured execution/input bindings, saved assembly hashes and
versions. All 40 Slurm allocations in the mixed invocation reached
`COMPLETED / 0:0`; its local setup task also completed. Scientific repeats remain
separate experimental records; their reference-completeness outcomes are not
output-agreement verdicts. The complete local contract suite passes 112 tests.
Owned-work cleanup was inspected on GPFS without deleting work or shared inputs.

The cold Quick result includes a measured incomplete long-read assembly. Successful
workflow execution means the pipeline recorded and assessed the output correctly;
it does not mean every reference was completely recovered. Short-read breadth and
fragmentation metrics remain separate from long-read single-alignment completion.

No full scientific panel was launched for these checks. Whole-genome Standard
performance, every declared collection, every optional assembler configuration and
scientific Docker execution are not claimed by this validation. The labelled pilot website is separate from the established scientific report
denominators; publication evidence is in `evidence/pilot-publication-v1/`.
