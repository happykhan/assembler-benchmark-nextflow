#!/usr/bin/env bash
#SBATCH --account=aanensen.prj
#SBATCH --partition=short
#SBATCH --nodes=2
#SBATCH --ntasks=2
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:05:00
#SBATCH --job-name=assembly-cache-probe
set -euo pipefail
probe=/well/aanensen/users/rva470/assembler-benchmark-refactor-20261113/preparation-probe
py=/well/aanensen/users/rva470/assembler-benchmark-refactor-20261113/tools/environments/.pixi/envs/default/bin/python
cd "$probe"
directory="$probe/two-node-$SLURM_JOB_ID"
mkdir "$directory"
export PYTHONPATH="$probe"
export NO_PROXY="*"
export no_proxy="*"
"$py" tests/fixtures/shared_cache_probe.py server "$directory" > "$directory/server.log" 2>&1 &
server_pid=$!
trap 'kill "$server_pid" 2>/dev/null || true' EXIT
for unused in $(seq 1 200); do test ! -e "$directory/server.json" || break; sleep .1; done
test -e "$directory/server.json"
srun --nodes=2 --ntasks=2 --ntasks-per-node=1 "$py" "$probe/tests/fixtures/shared_cache_probe.py" worker "$directory"
srun --nodes=2 --ntasks=2 --ntasks-per-node=1 "$probe/network-blocker" "$py" "$probe/tests/fixtures/shared_cache_probe.py" worker "$directory" --offline
"$py" tests/fixtures/shared_cache_probe.py verify "$directory"
