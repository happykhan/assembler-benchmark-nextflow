#!/usr/bin/env bash
cd /well/aanensen/users/rva470/assembler-benchmark-refactor-20261113
export PATH=/users/aanensen/rva470/.pixi/bin:$PATH
export NXF_ANSI_LOG=false
export JAVA_CMD=/well/aanensen/users/rva470/assembler-benchmark-nextflow/environments/.pixi/envs/default/bin/java
export PY=/well/aanensen/users/rva470/assembler-benchmark-refactor-20261113/tools/environments/.pixi/envs/default/bin/python
/well/aanensen/users/rva470/assembler-benchmark-nextflow/.tools/nextflow -log offline-final.nextflow.log run pipeline-offline-final -profile bmrc,pixi,apptainer --collections quick --offline --network_blocker /well/aanensen/users/rva470/assembler-benchmark-refactor-20261113/preparation-probe/network-blocker  --outdir current-offline-final --cache_dir cache-offline-final --bootstrap_python "$PY" -with-trace offline-final.trace.tsv -w work-offline-final
code=$?
printf '%s\n' "$code" > offline-final.exit
exit "$code"
