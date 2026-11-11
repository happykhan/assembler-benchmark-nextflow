#!/usr/bin/env bash
set -euo pipefail
cd /well/aanensen/users/rva470/assembler-benchmark-nextflow
export PATH=/well/aanensen/users/rva470/.cache/rattler/cached-envs-v0/mummer4-2eeacd5d28a50228/bin:/users/aanensen/rva470/.pixi/bin:$PATH
pixi run --locked --no-install --manifest-path environments/pixi.toml python evidence/assessment-diagnosis/mummer_check.py
