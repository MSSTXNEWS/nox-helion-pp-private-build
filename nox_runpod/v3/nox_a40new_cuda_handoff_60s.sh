#!/usr/bin/env bash
# NOX A40NEW: 60s CUDA-build watcher, safe one-time handoff to real GPU teacher.
set -Eeuo pipefail
R=/workspace/nox
D=/opt/nox_a40new
BIN=$D/llama.cpp/build/bin/llama-server
BASE=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/feature/nox-prime-v3-teachers-progress-20261110/nox_runpod/v3
mkdir -p "$D" "$R/logs"
exec 9>"$D/cuda_handoff.lock"
flock -n 9 || { echo NOX_CUDA_HANDOFF_ALREADY_RUNNING;exit 0; }
log(){ printf '%s %s\n' "$(date -u +%FT%TZ)" "$*" | tee -a "$R/logs/NOX_A40NEW_CUDA_HANDOFF.log"; }
for i in $(seq 1 360);do
 if ! [ -x "$BIN" ];then
  if pgrep -af 'cmake|nvcc|c\+\+' | grep -F '/opt/nox_a40new/llama.cpp' | grep -v grep >/dev/null;then
   ((i % 5 == 1)) && log CUDA_BUILD_RUNNING || true
   sleep 60;continue
  fi
  log CUDA_BUILD_NOT_RUNNING_REPAIR_BOOTSTRAP
 fi
 curl -fsSL --retry 3 "$BASE/nox_a40new_bootstrap.sh" -o "$D/nox_a40new_bootstrap.sh.tmp" || { log HOLD_BOOTSTRAP_DOWNLOAD; sleep 60;continue; }
 bash -n "$D/nox_a40new_bootstrap.sh.tmp" || { log HOLD_BOOTSTRAP_SYNTAX;exit 2; }
 mv -f "$D/nox_a40new_bootstrap.sh.tmp" "$D/nox_a40new_bootstrap.sh"
 if bash "$D/nox_a40new_bootstrap.sh" >>"$R/logs/NOX_A40NEW_CUDA_BOOTSTRAP.log" 2>&1;then
  log CUDA_BOOTSTRAP_EXIT_0
  sleep 10
  nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.free --format=csv,noheader | tee -a "$R/logs/NOX_A40NEW_CUDA_HANDOFF.log"
  cat "$R/dispatcher/nox_a40new/status.json" 2>/dev/null || true
  exit 0
 fi
 log CUDA_BOOTSTRAP_HOLD_CHECK_LOG
 sleep 60
done
log HOLD_CUDA_HANDOFF_RETRIES_EXHAUSTED
exit 2
