#!/usr/bin/env bash
# NOX A5000: keep the primary active training untouched; start CPU knowledge
# preparation immediately, and isolated GPU fine tuning only when VRAM permits.
set -Eeuo pipefail
R=/workspace/nox
S="$R/dispatcher/a5000_knowledge_background"
P="$R/tools/a5000_background_knowledge.py"
LOG="$R/logs"
mkdir -p "$S" "$LOG" "$R/tools"
GPU="$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)"
[[ "$GPU" == *"A5000"* ]] || { echo "HOLD_WRONG_GPU_$GPU"; exit 12; }
test -s "$R/models/NOX_9B_UNIFIED/NOX_UNIFIED_RECEIPT.json" || { echo "HOLD_UNIFIED_NOX_9B_MISSING";exit 13; }
test -x "$R/prime9b-venv/bin/python" || { echo "HOLD_TRAINING_VENV_MISSING";exit 14; }
exec 9>"$S/launch.lock"
flock -n 9 || { echo "NOX_BACKGROUND_ALREADY_STARTING";exit 0; }
if [ -s "$S/supervisor.pid" ] && kill -0 "$(cat "$S/supervisor.pid")" 2>/dev/null;then
  echo "NOX_A5000_KNOWLEDGE_ALREADY_RUNNING pid=$(cat "$S/supervisor.pid")";exit 0
fi
curl -fLsS --retry 4 'https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/75fb49044e4b5b5c48b4b2389c88ac221a9c01f0/nox_runpod/stage0/a5000_background_knowledge.py' -o "$P.new"
"$R/prime9b-venv/bin/python" -m py_compile "$P.new"
mv -f "$P.new" "$P"
cat > "$S/supervisor.sh" <<'BASH'
#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox
S="$R/dispatcher/a5000_knowledge_background"
exec 8>"$S/supervisor.lock"
flock -n 8 || exit 0
while [ ! -e "$S/STOP" ];do
 "$R/prime9b-venv/bin/python" -u "$R/tools/a5000_background_knowledge.py" \
  >>"$R/logs/NOX_A5000_KNOWLEDGE_BACKGROUND.log" 2>&1 || true
 echo "$(date -u +%FT%TZ) background worker restart" >>"$R/logs/NOX_A5000_KNOWLEDGE_RESTARTS.log"
 sleep 60
done
BASH
chmod 700 "$S/supervisor.sh"
nohup setsid bash "$S/supervisor.sh" </dev/null >/dev/null 2>&1 &
pid=$!
echo "$pid" > "$S/supervisor.pid"
sleep 3
kill -0 "$pid" 2>/dev/null || { echo "NOX_A5000_BACKGROUND_FAILED";tail -n 20 "$LOG/NOX_A5000_KNOWLEDGE_BACKGROUND.log" || true; exit 15; }
echo "NOX_A5000_BACKGROUND_KNOWLEDGE_STARTED pid=$pid"
echo "PRIMARY_N0X_TRAINER_UNTOUCHED"
echo "BACKGROUND_SNAPSHOT=$S/snapshot.json"
echo "GPU_TRAINING_ONLY_WHEN_VRAM_FREE_GE_12500MiB"
