#!/usr/bin/env bash
# A40: source-backed unification of THREE teachers' knowledge with S03.
# No GPU job interruption; no LoRA/QLoRA; no false claim of neural-weight merge.
set -Eeuo pipefail
R=/workspace/nox
S="$R/dispatcher/a40_unification"
mkdir -p "$S" "$R/tools" "$R/logs"
[[ "$(nvidia-smi --query-gpu=name --format=csv,noheader|head -1)" == *A40* ]] || { echo "HOLD_NOT_A40";exit 12; }
exec 9>"$S/start.lock"
flock -n 9 || { echo "NOX_A40_UNIFICATION_SETUP_ALREADY_RUNNING";exit 0; }
# Ensure source memory service is already running or starts once.
MEM_URL='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/5cef7521fe34c459b9a5d9ced6b1def20ee08b81/nox_runpod/stage0/start_a40_unified_nox_memory.sh'
curl -fsSL --retry 3 "$MEM_URL" | bash
URL='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/b43802c5c08697426bf0d3ecb78f1b7d2dd903aa/nox_runpod/stage0/a40_3teacher_unified_corpus.py'
curl -fsSL --retry 3 "$URL" -o "$R/tools/a40_3teacher_unified_corpus.py.new"
python3 -m py_compile "$R/tools/a40_3teacher_unified_corpus.py.new"
mv -f "$R/tools/a40_3teacher_unified_corpus.py.new" "$R/tools/a40_3teacher_unified_corpus.py"
if [ -s "$S/runner.pid" ] && kill -0 "$(cat "$S/runner.pid")" 2>/dev/null;then
 echo "NOX_3TEACHER_UNIFICATION_ALREADY_RUNNING pid=$(cat "$S/runner.pid")"
 exit 0
fi
cat >"$S/runner.sh" <<'SUP'
#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox
S="$R/dispatcher/a40_unification"
exec 8>"$S/runner.lock"
flock -n 8 || exit 0
while [ ! -e "$S/STOP" ];do
  nice -n 10 python3 -u "$R/tools/a40_3teacher_unified_corpus.py" >>"$R/logs/NOX_A40_3TEACHER_UNIFICATION.log" 2>&1 || true
  sleep 60
done
SUP
chmod 700 "$S/runner.sh"
nohup setsid bash "$S/runner.sh" </dev/null >> "$R/logs/NOX_A40_3TEACHER_SUPERVISOR.log" 2>&1 &
pid=$!;echo "$pid" >"$S/runner.pid"
sleep 3
kill -0 "$pid" 2>/dev/null || { echo "HOLD_UNIFICATION_SUPERVISOR_FAILED";exit 13; }
echo "NOX_A40_THREE_TEACHER_MEMORY_CONSOLIDATION_STARTED pid=$pid"
echo "NOX_STATUS=$S/status.json"
echo "NOX_CORPUS=$R/distillation/NOX_3TEACHER_UNIFIED"
echo "GPU_TEACHER_PROCESSES_UNTOUCHED; A5000_UNTOUCHED; NO_ADAPTERS"
