#!/usr/bin/env bash
# Initialize evidence-backed NOX self model on persistent shared volume, no restarts.
set -Eeuo pipefail
ROOT=/workspace/nox
SELF="$ROOT/memory/NOX_SELF_MODEL"
mkdir -p "$SELF" "$ROOT/tools" "$ROOT/logs"
exec 9>"$SELF/launch.lock"
flock -n 9 || { echo NOX_SELF_MODEL_LAUNCH_LOCKED;exit 0; }
PY="$ROOT/prime9b-venv/bin/python"
test -x "$PY" || PY=python3
URL='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/ea88d1d2816865e8e06228cca7a8fcca706e857a/nox_runpod/stage0/nox_functional_self_model.py'
curl -fsSL --retry 4 "$URL" -o "$ROOT/tools/nox_functional_self_model.py.new"
"$PY" -m py_compile "$ROOT/tools/nox_functional_self_model.py.new"
mv "$ROOT/tools/nox_functional_self_model.py.new" "$ROOT/tools/nox_functional_self_model.py"
if [ -s "$SELF/worker.pid" ] && kill -0 "$(cat "$SELF/worker.pid")" 2>/dev/null;then
 echo "NOX_SELF_MODEL_ALREADY_RUNNING pid=$(cat "$SELF/worker.pid")";exit 0
fi
cat > "$SELF/supervise.sh" <<'BASH'
#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox
S="$R/memory/NOX_SELF_MODEL"
exec 8>"$S/supervisor.lock"
flock -n 8 || exit 0
while [ ! -e "$S/STOP" ];do
 python3 -u "$R/tools/nox_functional_self_model.py" >>"$R/logs/NOX_SELF_MODEL.log" 2>&1 || true
 sleep 45
done
BASH
chmod 700 "$SELF/supervise.sh"
nohup setsid bash "$SELF/supervise.sh" </dev/null >>"$ROOT/logs/NOX_SELF_SUPERVISOR.log" 2>&1 &
pid=$!;echo "$pid" > "$SELF/worker.pid"
sleep 3
kill -0 "$pid" 2>/dev/null || { echo "NOX_SELF_MODEL_EARLY_EXIT";tail -n 15 "$ROOT/logs/NOX_SELF_MODEL.log";exit 1; }
echo "NOX_SELF_MODEL_DETACHED pid=$pid"
echo "NOX_SELF_MODEL_PATH=$SELF/self_model.json"
echo "NOX_PRIMARY_WEIGHTS_UNTOUCHED"
