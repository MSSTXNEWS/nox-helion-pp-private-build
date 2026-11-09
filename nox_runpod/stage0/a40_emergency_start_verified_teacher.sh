#!/usr/bin/env bash
# A40 emergency: start useful Qwen 9B teacher inference now, don't wait for other downloads.
set -Eeuo pipefail
R=/workspace/nox
S="$R/dispatcher/a40"
L="$R/logs"
VENV=/opt/nox_a40_dispatcher_venv
GGUF=/opt/nox_teachers/qwen9/Qwen3.5-9B-Q4_K_M.gguf
CLI=/opt/llama.cpp/build/bin/llama-cli
mkdir -p "$S" "$L" /opt/llama.cpp
test -s "$GGUF" || { echo "HOLD_QWEN9_WEIGHT_NOT_VERIFIED_OR_MISSING";exit 20; }
test -s /opt/nox_teachers/qwen9/receipt.json || { echo "HOLD_QWEN9_NO_HASH_RECEIPT";exit 21; }
test -x "$VENV/bin/python" || { echo "HOLD_DISPATCHER_VENV_MISSING";exit 22; }
test "$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1 | xargs)" = "NVIDIA A40" || { echo "HOLD_NOT_A40";exit 23; }
# Check that the existing qwen9 file still matches its verified receipt.
"$VENV/bin/python" - <<'PY'
import json,pathlib,hashlib
r=json.loads(pathlib.Path('/opt/nox_teachers/qwen9/receipt.json').read_text())
p=pathlib.Path('/opt/nox_teachers/qwen9/Qwen3.5-9B-Q4_K_M.gguf')
assert p.stat().st_size==r['bytes'], 'QWEN9_SIZE_MISMATCH'
h=hashlib.sha256()
with p.open('rb') as f:
 for x in iter(lambda:f.read(8*1024*1024),b''):h.update(x)
assert h.hexdigest()==r['sha256'], 'QWEN9_SHA_MISMATCH'
print('A40_QWEN9_DONOR_SHA_VERIFIED',flush=True)
PY
# Never share a write target with the ongoing A5000 trainer.
if [ -s "$S/emergency_qwen9.pid" ] && kill -0 "$(cat "$S/emergency_qwen9.pid")" 2>/dev/null; then
 echo "A40_QWEN9_ALREADY_RUNNING pid=$(cat "$S/emergency_qwen9.pid")"
 exit 0
fi
if ! test -x "$CLI"; then
 command -v git >/dev/null || { echo "HOLD_GIT_MISSING";exit 24; }
 command -v cmake >/dev/null || { echo "HOLD_CMAKE_MISSING";exit 25; }
 command -v nvcc >/dev/null || { echo "HOLD_NVCC_MISSING";exit 26; }
 echo "A40_LLAMA_CUDA_BUILD_BEGIN"
 if [ ! -d /opt/llama.cpp/.git ];then git clone --depth 1 --filter=blob:none https://github.com/ggml-org/llama.cpp.git /opt/llama.cpp;fi
 cmake -S /opt/llama.cpp -B /opt/llama.cpp/build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=86 -DCMAKE_BUILD_TYPE=Release
 cmake --build /opt/llama.cpp/build -j 6 --target llama-cli
fi
test -x "$CLI" || { echo "HOLD_LLAMA_CLI_MISSING";exit 27; }
WORKER_URL='https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/0d0ac95126370b37a8efc14ef7a84e574ad98fe8/nox_runpod/stage0/a40_three_teachers_worker.py'
curl -fLsS --retry 3 "$WORKER_URL" -o "$R/tools/a40_three_teachers_worker.py.new"
"$VENV/bin/python" -m py_compile "$R/tools/a40_three_teachers_worker.py.new"
mv -f "$R/tools/a40_three_teachers_worker.py.new" "$R/tools/a40_three_teachers_worker.py"
cat > "$S/emergency_qwen9.sh" <<'BASH'
#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox
S="$R/dispatcher/a40"
L="$R/logs"
VENV=/opt/nox_a40_dispatcher_venv/bin/python
exec 7>"$S/emergency_qwen9.lock"
flock -n 7 || exit 0
cyclefile="$S/emergency_qwen9_cycle"
cycle=0; [ ! -s "$cyclefile" ] || cycle="$(cat "$cyclefile")"
while [ ! -e "$S/STOP" ] && [ ! -e "$S/STOP_EMERGENCY_QWEN9" ]; do
 set +e
 NOX_CYCLE="$cycle" "$VENV" -u "$R/tools/a40_three_teachers_worker.py" \
  --id qwen9_A40 --model /opt/nox_teachers/qwen9/Qwen3.5-9B-Q4_K_M.gguf \
  --gpu-layers 50 --cli /opt/llama.cpp/build/bin/llama-cli --passes 1 \
  >>"$L/NOX_A40_QWEN9_LIVE.log" 2>&1
 rc=$?
 set -e
 if [ "$rc" -eq 0 ];then cycle=$((cycle+1)); printf '%s' "$cycle" > "$cyclefile";fi
 printf '%s result=%s cycle=%s\n' "$(date -u +%FT%TZ)" "$rc" "$cycle" >>"$L/NOX_A40_QWEN9_RESTARTS.log"
 # GPU must not be kept busy with bogus loops; wait after errors.
 [ "$rc" -eq 0 ] && sleep 3 || sleep 60
done
BASH
chmod 700 "$S/emergency_qwen9.sh"
nohup setsid bash "$S/emergency_qwen9.sh" </dev/null >>"$L/NOX_A40_QWEN9_SUPERVISOR.log" 2>&1 &
pid=$!
echo "$pid" > "$S/emergency_qwen9.pid"
sleep 3
kill -0 "$pid" 2>/dev/null || { echo "NOX_A40_QWEN9_EARLY_EXIT"; tail -n 20 "$L/NOX_A40_QWEN9_SUPERVISOR.log"; exit 28; }
echo "NOX_A40_QWEN9_GPU_TEACHER_DETACHED pid=$pid"
echo "NOX_A40_QWEN9_LOG=$L/NOX_A40_QWEN9_LIVE.log"
echo "NOX_A5000_TRAINING_UNTOUCHED"
