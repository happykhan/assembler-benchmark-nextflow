# Scoped operational work cleanup

Cleanup is optional and deliberate. It removes a finished **owned Nextflow work
root**, not a case result, scenario, scientific input cache or software cache.
It disables `-resume` for the removed task directories. Current packages remain
readable and the website can still be rendered from them.

Use a dedicated work root for a narrow cleanup scope:

```bash
nextflow run happykhan/assembler-benchmark-nextflow --collections quick \
  --cache_dir cache --outdir current -w work/quick-validation -profile bmrc,pixi
```

Controller start/completion hooks register a fresh empty work root and record its
lifecycle. They never delete data. A nonempty legacy/unowned root is preserved;
a normal run can still use it, but the cleanup command refuses it. Previously
owned work can be reused only with the same project, cache and current-result
bindings after its previous controller ends. It can then contain operational
tasks from several compatible invocations; use distinct `-w` roots for narrower
per-run scope.

Inspect first, from the recorded controller host after Nextflow exits:

```bash
python3 bin/cleanup.py --work-dir work/quick-validation
```

Dry-run is the default. It reports the exact owned root, file/link counts,
logical file bytes and protected cache/result locations. Logical bytes do not
promise physical disk space reclaimed. Shared-data symlinks are not traversed or
counted as owned input bytes. Inspection deletes nothing.

After reviewing that scope, explicit removal is:

```bash
python3 bin/cleanup.py --work-dir work/quick-validation --execute
```

Active/failed runs, a live controller, unknown controller state on another host,
missing/invalid ownership, symbolic-link roots, substituted directory identities,
protected ancestors and overlaps with scientific caches/current results are
refused. Existing current packages must validate before work is removed.
Successful plan-only/prepare-only runs do not need a result catalogue merely to
clean operational work. An external lifecycle lock prevents launch/cleanup races.
The validated root is detached atomically before its owned contents are removed;
unrelated neighbouring directories and shared-cache targets are untouched.

There is no force/adoption deletion bypass. A crash leaving an active marker
requires lifecycle investigation; it is not proof that work is disposable. Wait
for the controller to exit, not just for its completion hook to start. An
interrupted explicit removal may leave a `.removing-...` directory for review.
`begin` and `finish` are controller hooks, not manual prerequisites for users.

Tests exercise actual removal only inside disposable temporary fixtures. No
existing scientific work/cache data are deleted while implementing this feature.
