#!/usr/bin/env bash
# NOX dual A40 launcher: new 3 concurrent GPU teacher streams;
# old trainer remains protected; 60s guardian with append-only journal.
set -Eeuo pipefail
NODE="$1"
case "$NODE" in A40|A40NEW);;*)exit 2;;esac
R=/workspace/nox
BASE=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/feature/nox-prime-v3-teachers-progress-20261110/nox_runpod/v3
G=/opt/nox_guardian/bin
mkdir -p "$G" "$R/logs"
curl -fsSL --retry 3 --connect-timeout 15 "$BASE/nox_guardian_60s.py" -o "/tmp/nox_guardian_${NODE}_$.py"
python3 -m py_compile "/tmp/nox_guardian_${NODE}_$.py"
install -m 644 "/tmp/nox_guardian_${NODE}_$.py" "$G/nox_guardian_60s.py"
rm -f "/tmp/nox_guardian_${NODE}_$.py"
if [ "$NODE" = A40NEW ];then
 curl -fsSL --retry 3 "$BASE/nox_a40new_bootstrap.sh" -o /tmp/nox_a40new_start.sh
 bash -n /tmp/nox_a40new_start.sh
 bash /tmp/nox_a40new_start.sh
else
 curl -fsSL --retry 3 "$BASE/nox_v3_repair_immediate.sh" -o /tmp/nox_a40_v3_repair.sh
 bash -n /tmp/nox_a40_v3_repair.sh
 bash /tmp/nox_a40_v3_repair.sh A40
fi
# One guardian process, 60s journal; avoid duplicates.
if ! pgrep -f "^python3 -u $G/nox_guardian_60s.py --node $NODE$" >/dev/null;then
 nohup python3 -u "$G/nox_guardian_60s.py" --node "$NODE" >>"$R/logs/NOX_GUARDIAN_$NODE.log" 2>&1 </dev/null &
 echo "GUARDIAN_60S_STARTED_$NODE PID=$!"
else echo "GUARDIAN_60S_ALREADY_RUNNING_$NODE";fi
echo "===GPU==="
nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.free --format=csv,noheader
echo "===STATUS==="
if [ "$NODE" = A40NEW ];then
 cat "$R/dispatcher/nox_a40new/status.json" 2>/dev/null || true
 tail -n 6 "$R/logs/NOX_A40NEW_TEACHERS.log" 2>/dev/null || true
else
 cat "$R/dispatcher/nox_v3/orchestrator_status_A40.json" 2>/dev/null || true
fi
