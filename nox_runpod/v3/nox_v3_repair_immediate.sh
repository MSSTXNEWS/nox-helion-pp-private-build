#!/usr/bin/env bash
# NOX PRIME V3 immediate one-shot repair, no Pod restart or deleting checkpoints.
set -Eeuo pipefail
NODE="${1:?use A40 or A5000}"
case "$NODE" in A40|A5000);;*) exit 2;;esac
R=/workspace/nox
S="$R/dispatcher/nox_v3"
B="$S/bin"
BASE=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/feature/nox-prime-v3-teachers-progress-20261110
mkdir -p "$B" "$R/logs"
exec 9>"$S/repair_$NODE.lock"
flock -n 9 || { echo "REPAIR_ALREADY_RUNNING_$NODE";exit 0; }
for n in nox_v3_dispatcher.py nox_v3_supervisor.py nox_v3_cutover.py nox_v3_keeper.py nox_watchdog_10s.py nox_activate_idle_v3.py nox_force_work_now.py nox_teacher_server_batch.py nox_teacher_s03_import.py nox_progress_v3.py nox_adaptive_swarm.py nox_improvement_loop.py nox_self_model.py nox_stage_27b_to_shared.py;do
 t="$B/$n.$NODE.$$.new"
 if curl -fsSL --retry 3 --connect-timeout 15 --max-time 110 "$BASE/nox_runpod/v3/$n" -o "$t" && python3 -m py_compile "$t";then
   if ! cmp -s "$t" "$B/$n";then mv -f "$t" "$B/$n";else rm -f "$t";fi
 else rm -f "$t";echo "HOLD_UPDATE_$n";fi
done
t="$B/a40_full_parameter_distill_cycle.py.$NODE.$$.new"
if curl -fsSL --retry 3 --connect-timeout 15 --max-time 110 "$BASE/nox_runpod/stage0/a40_full_parameter_distill_cycle.py" -o "$t" && python3 -m py_compile "$t";then
  if ! cmp -s "$t" "$B/a40_full_parameter_distill_cycle.py";then mv -f "$t" "$B/a40_full_parameter_distill_cycle.py";else rm -f "$t";fi
else rm -f "$t";echo HOLD_TRAINER_UPDATE;fi
echo "REPAIR_FILES_APPLIED_$NODE"
# A currently active full-weight trainer owns its GPU. Do not double-start it.
if [ "$NODE" = A40 ] && pgrep -f 'a40_full_parameter_distill_cycle.py --cycle' >/dev/null;then
 echo "TRAINER_IN_FLIGHT_PRESERVED"
else
 python3 "$B/nox_activate_idle_v3.py" --node "$NODE" || true
 python3 "$B/nox_v3_supervisor.py" --node "$NODE" || true
fi
# Autonomous check: one 10s watchdog per node, checked against exact argv.
if ! pgrep -f "^python3 -u /workspace/nox/dispatcher/nox_v3/bin/nox_watchdog_10s.py --node $NODE$" >/dev/null;then
 nohup python3 -u "$B/nox_watchdog_10s.py" --node "$NODE" >>"$R/logs/NOX_WATCHDOG_10S_$NODE.log" 2>&1 </dev/null &
 echo "WATCHDOG_STARTED PID=$!"
fi
echo ===GPU===
nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.free,temperature.gpu --format=csv,noheader || true
echo ===GPU_OWNERS===
nvidia-smi --query-compute-apps=pid,process_name,used_gpu_memory --format=csv,noheader || true
echo ===NOX_STATUS===
cat "$S/orchestrator_status_$NODE.json" 2>/dev/null || true
echo ===TRAINER_STATUS===
if [ "$NODE" = A40 ];then cat "$R/dispatcher/a40_full_parameter/progress.json" 2>/dev/null || true;fi
echo ===LOG===
tail -n 14 "$R/logs/NOX_V3_$NODE.log" 2>/dev/null || true
