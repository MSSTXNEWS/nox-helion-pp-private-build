#!/usr/bin/env bash
# Install completely fresh worker on the NEW A40. Shared weights are re-used.
set -Eeuo pipefail
R=/workspace/nox
S=$R/dispatcher/nox_a40new
B=/opt/nox_a40new/bin
BASE=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/feature/nox-prime-v3-teachers-progress-20261110
mkdir -p "$B" "$R/logs"
findmnt -n /workspace >/dev/null || { echo HOLD_SHARED_VOLUME_NOT_MOUNTED;exit 2; }
test -d "$R/teachers" || { echo HOLD_NO_TEACHERS_IN_SHARED_VOLUME;exit 2; }
for n in nox_a40new_teacher_controller.py nox_teacher_server_batch.py nox_a40new_cutover_cpu_only.py;do
 tmp="$B/$n.$$.new"
 curl -fsSL --retry 3 "$BASE/nox_runpod/v3/$n" -o "$tmp"
 python3 -m py_compile "$tmp"
 mv -f "$tmp" "$B/$n"
done
# Reject the existing shared CPU-only llama-server.
# Build an actual CUDA binary on NEW A40's local disk, not shared /workspace.
D=/opt/nox_a40new/llama.cpp
GPU_BIN="$D/build/bin/llama-server"
if [ ! -x "$GPU_BIN" ];then
 if ! command -v nvcc >/dev/null 2>&1;then echo HOLD_CUDA_COMPILER_MISSING; exit 3;fi
 for dep in git cmake c++;do command -v "$dep" >/dev/null 2>&1 || { echo "HOLD_MISSING_$dep";exit 3; };done
 if [ ! -d "$D/.git" ];then
  mkdir -p /opt/nox_a40new
  git clone --depth 1 https://github.com/ggml-org/llama.cpp.git "$D"
 fi
 cmake -S "$D" -B "$D/build" -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release
 cmake --build "$D/build" --target llama-server -j 3
fi
test -x "$GPU_BIN" || { echo HOLD_CUDA_LLAMA_BINARY_MISSING;exit 3; }
if ! "$GPU_BIN" --help 2>&1 | grep -qi 'gpu-layers';then
 echo HOLD_LLAMA_GPU_OPTION_MISSING;exit 3
fi
echo "NOX_A40NEW_DEDICATED_GPU_SERVER_READY $GPU_BIN"
python3 "$B/nox_a40new_cutover_cpu_only.py"
if ! pgrep -f "^python3 -u $B/nox_a40new_teacher_controller.py$" >/dev/null;then
 nohup python3 -u "$B/nox_a40new_teacher_controller.py" >>"$R/logs/NOX_A40NEW_CONTROLLER.log" 2>&1 </dev/null &
 echo "NEW_A40_CONTROLLER_PID=$!"
else echo NEW_A40_CONTROLLER_ALREADY_RUNNING;fi
sleep 3
echo === NEW_A40_GPU ===
nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.free --format=csv,noheader || true
echo === NEW_A40_STATUS ===
cat "$S/status.json" 2>/dev/null || echo STATUS_PENDING
