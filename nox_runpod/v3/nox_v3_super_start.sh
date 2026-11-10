#!/usr/bin/env bash
# NOX PRIME V3: safe no-loss bootstrap. Does not activate training until cutover is proven.
set -Eeuo pipefail
NODE="$1"
case "$NODE" in A40|A5000) ;; *) echo 'USAGE: nox_v3_super_start.sh A40|A5000'; exit 2;; esac
R=/workspace/nox
S=$R/dispatcher/nox_v3
BIN=$S/bin
BRANCH=feature/nox-prime-v3-teachers-progress-20261110
BASE=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/$BRANCH
mkdir -p "$S" "$BIN" "$R/logs"
exec 9>"$S/install_$NODE.lock"
flock -n 9 || { echo NOX_V3_INSTALL_ALREADY_RUNNING_NO_DUPLICATE; exit 0; }
for name in nox_v3_dispatcher.py nox_progress_v3.py nox_teacher_gguf_batch.py nox_teacher_server_batch.py nox_stage_27b_to_shared.py nox_self_model.py nox_improvement_loop.py nox_adaptive_swarm.py nox_teacher_s03_import.py nox_v3_cutover.py nox_v3_supervisor.py nox_v3_keeper.py; do
  curl -fsSL --retry 3 "$BASE/nox_runpod/v3/$name" -o "$BIN/$name.tmp"
  python3 -m py_compile "$BIN/$name.tmp"
  mv "$BIN/$name.tmp" "$BIN/$name"
done
curl -fsSL --retry 3 "$BASE/nox_runpod/stage0/a40_full_parameter_distill_cycle.py" -o "$BIN/a40_full_parameter_distill_cycle.py.tmp"
python3 -m py_compile "$BIN/a40_full_parameter_distill_cycle.py.tmp"
mv "$BIN/a40_full_parameter_distill_cycle.py.tmp" "$BIN/a40_full_parameter_distill_cycle.py"
if [ ! -f "$S/NOX_PRIME_V3_PLAN.json" ];then
  curl -fsSL --retry 3 "$BASE/nox_runpod/v3/NOX_PRIME_V3_PLAN.json" -o "$S/NOX_PRIME_V3_PLAN.json.tmp"
  python3 -m json.tool "$S/NOX_PRIME_V3_PLAN.json.tmp" >/dev/null
  mv "$S/NOX_PRIME_V3_PLAN.json.tmp" "$S/NOX_PRIME_V3_PLAN.json"
else
  python3 -m json.tool "$S/NOX_PRIME_V3_PLAN.json" >/dev/null
  echo "NOX_V3_KEEP_LOCAL_CUTOVER_STATE"
fi
curl -fsSL --retry 3 "$BASE/nox_runpod/v3/NOX_WOW50_IDENTITY.json" -o "$S/NOX_WOW50_IDENTITY.json.tmp"
python3 -m json.tool "$S/NOX_WOW50_IDENTITY.json.tmp" >/dev/null
mv "$S/NOX_WOW50_IDENTITY.json.tmp" "$S/NOX_WOW50_IDENTITY.json"
if [ "$NODE" = A5000 ]; then
  python3 "$BIN/nox_stage_27b_to_shared.py" || echo HOLD_STAGE_27B_KEEP_ORIGINAL
fi
if [ "$NODE" = A40 ]; then
  curl -fsSL --retry 3 "$BASE/nox_runpod/v3/nox_prepare_llama_cpp.sh" -o "$BIN/nox_prepare_llama_cpp.sh"
  bash "$BIN/nox_prepare_llama_cpp.sh" || echo HOLD_LLAMA_RUNTIME
  curl -fsSL --retry 3 "$BASE/nox_runpod/v3/nox_download_32b.sh" -o "$BIN/nox_download_32b.sh"
  bash "$BIN/nox_download_32b.sh" || echo HOLD_32B_DOWNLOAD_KEEP_PART
fi
PIDFILE="$S/dispatcher_$NODE.pid"
if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [[ "$PID" =~ ^[0-9]+$ ]] && kill -0 "$PID" 2>/dev/null; then
    ARGS="$(ps -p "$PID" -o args= || true)"
    if [[ "$ARGS" == *nox_v3_dispatcher.py* && "$ARGS" == *"--node $NODE"* ]];then
      echo "NOX_V3_DISPATCHER_ALREADY_RUNNING NODE=$NODE PID=$PID"
      exit 0
    fi
  fi
fi
nohup python3 -u "$BIN/nox_v3_dispatcher.py" --node "$NODE" >>"$R/logs/NOX_V3_$NODE.log" 2>&1 </dev/null &
PID=$!
echo "$PID" > "$PIDFILE"
sleep 2
if kill -0 "$PID" 2>/dev/null; then echo "NOX_V3_PREPARED NODE=$NODE PID=$PID"; else echo HOLD_DISPATCHER_START;exit 3;fi
