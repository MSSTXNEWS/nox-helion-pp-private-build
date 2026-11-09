#!/usr/bin/env bash
# Fix only NOX source-memory controller, retain teacher CUDA processes and checkpoints.
set -Eeuo pipefail
R=/workspace/nox
S="$R/dispatcher/NOX_MULTI_GPU"
mkdir -p "$R/tools" "$S" "$R/logs"
exec 9>"$S/memory_hotfix.lock"
flock -n 9 || { echo "NOX_MEMORY_HOTFIX_ALREADY_RUNNING";exit 0; }
url='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/d579ae92fdec14eb31014dfd781c740bffa2ce08/nox_runpod/stage0/nox_no_adapter_multigpu_controller.py'
tmp="$R/tools/nox_no_adapter_multigpu_controller.py.hotfix"
curl -fLsS --retry 3 "$url" -o "$tmp"
python3 -m py_compile "$tmp"
mv -f "$tmp" "$R/tools/nox_no_adapter_multigpu_controller.py"
# Terminate ONLY controller Python process so existing bash supervisor reloads updated code.
# No model, teacher, CUDA worker or checkpoint process is signalled.
ps -eo pid=,comm=,args= | awk '$2 ~ /^python/ && $0 ~ /nox_no_adapter_multigpu_controller.py --role/ {print $1}' | while read -r pid; do
  [ -n "$pid" ] || continue
  kill -TERM "$pid" || true
  echo "NOX_RESOURCE_CONTROLLER_RELOAD_REQUESTED pid=$pid"
done
echo "NOX_S03_NETWORK_SQLITE_LOCKING_REMOVED"
echo "NOX_TEACHERS_AND_TRAINING_UNTOUCHED"
echo "NOX_MEMORY_SOURCE=/workspace/nox/memory/THREE_TEACHERS/knowledge_sources.jsonl"
