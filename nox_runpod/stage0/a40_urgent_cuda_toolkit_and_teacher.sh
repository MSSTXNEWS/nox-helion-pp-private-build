#!/usr/bin/env bash
# NOX A40 urgent CUDA repair, start a real verified 9B teacher immediately.
# GPU model files and base NOX checkpoints never overwritten.
set -Eeuo pipefail
R=/workspace/nox
S="$R/dispatcher/a40"
LOG="$R/logs"
VENV=/opt/nox_a40_dispatcher_venv
MODEL=/opt/nox_teachers/qwen9/Qwen3.5-9B-Q4_K_M.gguf
mkdir -p "$S" "$LOG" /opt/llama.cpp
exec 9>"$S/urgent_cuda_repair.lock"
flock -n 9 || { echo "NOX_A40_URGENT_SETUP_ALREADY_RUNNING";exit 0; }
test -s "$MODEL" && test -s /opt/nox_teachers/qwen9/receipt.json || { echo HOLD_NO_VERIFIED_QWEN9;exit 20; }
test -x "$VENV/bin/python" || { echo HOLD_VENV_MISSING;exit 21; }
if ! test -x /opt/llama.cpp/build/bin/llama-cli;then
  echo "NOX_A40_CUDA_BUILD_BEGIN"
  "$VENV/bin/python" -m pip install -q --no-cache-dir nvidia-cuda-nvcc-cu12 nvidia-cuda-runtime-cu12 nvidia-cuda-cccl-cu12 || true
  nvcc_path="$(find "$VENV/lib" -type f -name nvcc 2>/dev/null | head -1)"
  if [ -n "$nvcc_path" ];then
    chmod +x "$nvcc_path" || true
    export CUDACXX="$nvcc_path"
    export CUDA_HOME="$(dirname "$(dirname "$nvcc_path")")"
    export PATH="$(dirname "$nvcc_path"):$PATH"
  fi
  if [ ! -d /opt/llama.cpp/.git ];then
    git clone --depth 1 --filter=blob:none https://github.com/ggml-org/llama.cpp.git /opt/llama.cpp
  fi
  mkdir -p /opt/llama.cpp/build
  if [ -n "$nvcc_path" ] && cmake -S /opt/llama.cpp -B /opt/llama.cpp/build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=86 -DCMAKE_BUILD_TYPE=Release >>"$LOG/NOX_A40_CUDA_BUILD.log" 2>&1 && cmake --build /opt/llama.cpp/build --target llama-cli -j 6 >>"$LOG/NOX_A40_CUDA_BUILD.log" 2>&1;then
     echo "NOX_A40_CUDA_BINARY_BUILT"
  else
     echo "NOX_A40_CUDA_BUILD_UNAVAILABLE_ATTEMPT_CPU_BACKEND"
     cmake -S /opt/llama.cpp -B /opt/llama.cpp/build -DGGML_CUDA=OFF -DCMAKE_BUILD_TYPE=Release >>"$LOG/NOX_A40_CPU_BUILD.log" 2>&1
     cmake --build /opt/llama.cpp/build --target llama-cli -j 6 >>"$LOG/NOX_A40_CPU_BUILD.log" 2>&1
     echo "NOX_A40_CPU_BINARY_BUILT_GPU_BACKEND_NOT_YET_READY"
  fi
fi
test -x /opt/llama.cpp/build/bin/llama-cli || { echo "HOLD_BINARY_MISSING";exit 22; }
WORKER="$R/tools/a40_three_teachers_worker.py"
test -s "$WORKER" || { echo "HOLD_WORKER_MISSING";exit 23; }
if [ -s "$S/emergency_qwen9.pid" ] && kill -0 "$(cat "$S/emergency_qwen9.pid")" 2>/dev/null;then
 echo "NOX_A40_TEACHER_ALREADY_RUNNING";exit 0
fi
cat > "$S/urgent_worker.sh" <<'BASH'
#!/usr/bin/env bash
set -Eeuo pipefail
R=/workspace/nox
S="$R/dispatcher/a40"
L="$R/logs"
exec 7>"$S/urgent_worker.lock"
flock -n 7 || exit 0
cyclefile="$S/urgent_cycle.txt"
cycle=0
test ! -s "$cyclefile" || cycle="$(cat "$cyclefile")"
while [ ! -e "$S/STOP" ] && [ ! -e "$S/STOP_EMERGENCY_QWEN9" ]; do
 if [ -s "$S/NOX_GPU_BACKEND_READY" ];then layers=50;else layers=0;fi
 set +e
 NOX_CYCLE="$cycle" /opt/nox_a40_dispatcher_venv/bin/python -u "$R/tools/a40_three_teachers_worker.py" --id qwen9_A40 --model /opt/nox_teachers/qwen9/Qwen3.5-9B-Q4_K_M.gguf --gpu-layers "$layers" --cli /opt/llama.cpp/build/bin/llama-cli --passes 1 >>"$L/NOX_A40_QWEN9_LIVE.log" 2>&1
 rc=$?
 set -e
 if [ "$rc" -eq 0 ];then cycle=$((cycle+1));echo "$cycle" >"$cyclefile";fi
 echo "$(date -u +%FT%TZ) exit=$rc cycle=$cycle" >>"$L/NOX_A40_QWEN9_RESTARTS.log"
 sleep 45
done
BASH
chmod 700 "$S/urgent_worker.sh"
# Mark GPU backend only if libggml-cuda present.
if find /opt/llama.cpp/build -type f -name '*ggml-cuda*.so' | grep -q .;then echo yes > "$S/NOX_GPU_BACKEND_READY";fi
nohup setsid bash "$S/urgent_worker.sh" </dev/null >>"$LOG/NOX_A40_QWEN9_SUPERVISOR.log" 2>&1 &
pid=$!;echo "$pid" > "$S/emergency_qwen9.pid"
sleep 3
kill -0 "$pid" 2>/dev/null || { echo "HOLD_A40_WORKER_FAILED";tail -n 15 "$LOG/NOX_A40_QWEN9_LIVE.log" || true;exit 24; }
echo "NOX_A40_TEACHER_RUNNING pid=$pid"
if [ -s "$S/NOX_GPU_BACKEND_READY" ];then echo "NOX_A40_CUDA_BACKEND_READY";else echo "NOX_A40_CPU_FALLBACK_ACTIVE_GPU_NOT_ACCELERATED";fi
echo "NOX_A5000_UNTOUCHED"
