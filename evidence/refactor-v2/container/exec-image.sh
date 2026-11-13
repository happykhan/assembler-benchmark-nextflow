#!/usr/bin/env bash
#SBATCH --account=aanensen.prj
#SBATCH --partition=short
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:02:00
#SBATCH --job-name=assembly-sif-probe
set -euo pipefail
root=/well/aanensen/users/rva470/assembler-benchmark-refactor-20261113
probe="$root/container-probe"
image="$root/cache/images/702f3a3c966aa63a0a57906466ec33ce9a463b532446f5584498fa429d069fd8.sif"
blocker="$root/preparation-probe/network-blocker"
cd "$probe"
printf '%s\n' "$SLURM_JOB_ID" > exec-job-id.txt
hostname > exec-node.txt
apptainer exec --cleanenv --bind "$root:$root:ro" --pwd "$probe" "$image" pixi --version > pixi-version.txt 2> exec-engine.log
apptainer exec --cleanenv --bind "$root:$root:ro" --pwd "$probe" "$image" /bin/sh -c 'exec "$1" pixi --version' sh "$blocker" > pixi-version-blocked.txt 2>> exec-engine.log
apptainer exec --cleanenv --bind "$root:$root:ro" --pwd "$probe" "$image" "$blocker" --probe > container-network-probe.json 2>> exec-engine.log
cmp pixi-version.txt pixi-version-blocked.txt
cat pixi-version.txt container-network-probe.json
