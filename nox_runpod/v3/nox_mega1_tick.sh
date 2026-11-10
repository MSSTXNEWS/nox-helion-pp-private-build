#!/usr/bin/env bash
# NOX PRIME MEGA-1: idempotent fast bootstrap and every-3-min update tick.
# Does not restart containers, kill GPU work, delete checkpoints, or force cutover.
set -Eeuo pipefail
NODE="${1:?usage: nox_mega1_tick.sh A40|A5000}"
case "$NODE" in A40|A5000) ;; *) echo HOLD_INVALID_NODE;exit 2;; esac
R=/workspace/nox
S=$R/dispatcher/nox_v3
BIN=$S/bin
BASE=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/feature/nox-prime-v3-teachers-progress-20261110/nox_runpod/v3
mkdir -p "$S" "$BIN" "$R/logs"
exec 9>"$S/mega1_tick_$NODE.lock"
flock -n 9 || { echo "NOX_MEGA1_TICK_ALREADY_ACTIVE_$NODE";exit 0; }
ok=0
for name in nox_v3_dispatcher.py nox_v3_keeper.py nox_v3_cutover.py nox_v3_supervisor.py nox_teacher_server_batch.py nox_teacher_s03_import.py nox_stage_27b_to_shared.py nox_progress_v3.py nox_self_model.py nox_improvement_loop.py nox_adaptive_swarm.py nox_wow_acquire.py; do
 tmp="$BIN/$name.$NODE.$$.new"
 if curl --connect-timeout 15 --max-time 75 -fsSL --retry 2 "$BASE/$name" -o "$tmp" && python3 -m py_compile "$tmp"; then
  if ! cmp -s "$tmp" "$BIN/$name" 2>/dev/null;then mv -f "$tmp" "$BIN/$name";echo "NOX_UPDATED $name";else rm -f "$tmp";fi
 else
  rm -f "$tmp";echo "HOLD_SOURCE_UPDATE $name";ok=1
 fi
done
# Full-parameter trainer cannot be swapped while running, and is only read at
# the start of the next bounded optimizer cycle.
tmp="$BIN/a40_full_parameter_distill_cycle.py.$NODE.$$.new"
TRAIN=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/feature/nox-prime-v3-teachers-progress-20261110/nox_runpod/stage0/a40_full_parameter_distill_cycle.py
if curl --connect-timeout 15 --max-time 90 -fsSL --retry 2 "$TRAIN" -o "$tmp" && python3 -m py_compile "$tmp";then
 if ! cmp -s "$tmp" "$BIN/a40_full_parameter_distill_cycle.py" 2>/dev/null;then mv -f "$tmp" "$BIN/a40_full_parameter_distill_cycle.py";else rm -f "$tmp";fi
else rm -f "$tmp";echo HOLD_FULL_TRAINER_SOURCE;ok=1;fi
for name in NOX_MODEL_REGISTRY.json NOX_WOW_MAX_MANIFEST.json NOX_WOW50_IDENTITY.json;do
 tmp="$S/$name.$NODE.$$.new"
 if curl --connect-timeout 15 --max-time 75 -fsSL --retry 2 "$BASE/$name" -o "$tmp" && python3 -m json.tool "$tmp" >/dev/null;then
  if ! cmp -s "$tmp" "$S/$name" 2>/dev/null;then mv -f "$tmp" "$S/$name";else rm -f "$tmp";fi
 else rm -f "$tmp";echo "HOLD_MANIFEST_$name";ok=1;fi
done
if [ ! -s "$S/NOX_PRIME_V3_PLAN.json" ];then
 tmp="$S/NOX_PRIME_V3_PLAN.json.$NODE.$$.new"
 curl --connect-timeout 15 -fsSL --retry 2 "$BASE/NOX_PRIME_V3_PLAN.json" -o "$tmp"
 python3 -m json.tool "$tmp" >/dev/null
 mv -f "$tmp" "$S/NOX_PRIME_V3_PLAN.json"
fi
# Start the keeper in its own loop. Its lock and GPU ownership gates prevent
# duplicating dispatchers. Existing GPU tasks remain owned by their original PIDs.
if [ -s "$BIN/nox_v3_keeper.py" ];then
  pidfile="$S/keeper_$NODE.pid"
  old="$(cat "$pidfile" 2>/dev/null || true)"
  if ! [[ "$old" =~ ^[0-9]+$ ]] || ! kill -0 "$old" 2>/dev/null ||
      ! ps -p "$old" -o args= | grep -Fq "nox_v3_keeper.py --node $NODE";then
    nohup python3 -u "$BIN/nox_v3_keeper.py" --node "$NODE" >>"$R/logs/NOX_V3_KEEPER_$NODE.log" 2>&1 </dev/null &
    echo "$!" > "$pidfile"
    echo "NOX_KEEPER_STARTED_$NODE PID=$!"
  else echo "NOX_KEEPER_RUNNING_$NODE PID=$old";fi
fi
# Long downloads do not block dispatcher activation; resume on next invocation.
launch_once(){
 local tag="$1";shift
 local pidfile="$S/background_${tag}_$NODE.pid"
 local old="$(cat "$pidfile" 2>/dev/null || true)"
 if [[ "$old" =~ ^[0-9]+$ ]] && kill -0 "$old" 2>/dev/null;then return;fi
 nohup "$@" >>"$R/logs/NOX_V3_${tag}_$NODE.log" 2>&1 </dev/null &
 echo "$!" > "$pidfile"
 echo "NOX_BACKGROUND_${tag}_$NODE PID=$!"
}
if [ "$NODE" = A5000 ];then
 launch_once STAGE27 python3 "$BIN/nox_stage_27b_to_shared.py"
 launch_once WOW python3 "$BIN/nox_wow_acquire.py" --node A5000
fi
if [ "$NODE" = A40 ];then
 for script in nox_prepare_llama_cpp.sh nox_download_32b.sh;do
  tmp="$BIN/$script.$NODE.$$.new"
  if curl --connect-timeout 15 --max-time 75 -fsSL --retry 2 "$BASE/$script" -o "$tmp";then mv -f "$tmp" "$BIN/$script";else rm -f "$tmp";echo "HOLD_$script";fi
 done
 if [ -s "$BIN/nox_prepare_llama_cpp.sh" ];then launch_once LLAMA bash "$BIN/nox_prepare_llama_cpp.sh";fi
 if [ -s "$BIN/nox_download_32b.sh" ];then launch_once DEEPSEEK32 bash "$BIN/nox_download_32b.sh";fi
fi
echo "NOX_MEGA1_TICK_$NODE SOURCE_STATUS=$ok"
