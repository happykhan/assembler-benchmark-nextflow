#!/usr/bin/env bash
cd /well/aanensen/users/rva470/assembler-benchmark-refactor-20261113
export PATH=/users/aanensen/rva470/.pixi/bin:$PATH
export NXF_ANSI_LOG=false
export JAVA_CMD=/well/aanensen/users/rva470/assembler-benchmark-nextflow/environments/.pixi/envs/default/bin/java
export PY=/well/aanensen/users/rva470/assembler-benchmark-refactor-20261113/tools/environments/.pixi/envs/default/bin/python
/well/aanensen/users/rva470/assembler-benchmark-nextflow/.tools/nextflow -log offline-cold.nextflow.log run pipeline -profile bmrc,pixi,apptainer --collections quick --offline --network_blocker /well/aanensen/users/rva470/assembler-benchmark-refactor-20261113/preparation-probe/network-blocker  --outdir current-offline-cold --cache_dir cache-offline-cold --bootstrap_python "$PY" -with-trace offline-cold.trace.tsv -w work-offline-cold
code=$?
printf '%s\n' "$code" > offline-cold.exit
exit "$code"
