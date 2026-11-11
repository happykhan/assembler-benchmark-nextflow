#!/usr/bin/env bash
set -euo pipefail
cd /well/aanensen/users/rva470/assembler-benchmark-nextflow
/users/aanensen/rva470/.pixi/bin/pixi run --locked --no-install --manifest-path environments/pixi.toml python evidence/fragmentation-review/read_geometry.py --root /well/aanensen/users/rva470/assembler-benchmark-nextflow --out evidence/fragmentation-review/read-geometry.json
