#!/usr/bin/env bash
# Install completely fresh worker on the NEW A40. Shared weights are re-used.
set -Eeuo pipefail
R=/workspace/nox
S=$R/dispatcher/nox_a40new
B=$S/bin
BASE=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/feature/nox-prime-v3-teachers-progress-20261110
mkdir -p "$B" "$R/logs"
findmnt -n /workspace >/dev/null || { echo HOLD_SHARED_VOLUME_NOT_MOUNTED;exit 2; }
test -d "$R/teachers" || { echo HOLD_NO_TEACHERS_IN_SHARED_VOLUME;exit 2; }
for n in nox_a40new_teacher_controller.py nox_teacher_server_batch.py;do
 tmp="$B/$n.$$.new"
 curl -fsSL --retry 3 "$BASE/nox_runpod/v3/$n" -o "$tmp"
 python3 -m py_compile "$tmp"
 mv -f "$tmp" "$B/$n"
done
# A GPU-enabled llama-server is required. Prefer existing shared executable,
# otherwise build independently on NEW Pod's container disk (no old-Pod mutation).
if ! command -v llama-server >/dev/null 2>&1 && [ ! -x "$R/tools/llama.cpp/build/bin/llama-server" ];then
 if ! command -v nvcc >/dev/null 2>&1;then echo HOLD_CUDA_COMPILER_MISSING;exit 3;fi
 for n in git cmake c++;do command -v "$n" >/dev/null 2>&1 || { echo "HOLD_MISSING_$n";exit 3; };done
 D=/opt/nox_a40new/llama.cpp
 if [ ! -d "$D/.git" ];then mkdir -p /opt/nox_a40new;git clone --depth 1 https://github.com/ggml-org/llama.cpp.git "$D";fi
 cmake -S "$D" -B "$D/build" -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release
 cmake --build "$D/build" --target llama-server -j 3
 install -m755 "$D/build/bin/llama-server" /usr/local/bin/llama-server
fi
if ! pgrep -af 'nox_a40new_teacher_controller.py' | grep -F "$B/nox_a40new_teacher_controller.py" | grep -v grep >/dev/null;then
 nohup python3 -u "$B/nox_a40new_teacher_controller.py" >>"$R/logs/NOX_A40NEW_CONTROLLER.log" 2>&1 </dev/null &
 echo "NEW_A40_CONTROLLER_PID=$!"
else echo NEW_A40_CONTROLLER_ALREADY_RUNNING;fi
sleep 3
echo === NEW_A40_GPU ===
nvidia-smi --query-gpu=name,utilization.gpu,memory.used,memory.free --format=csv,noheader || true
echo === NEW_A40_STATUS ===
cat "$S/status.json" 2>/dev/null || echo STATUS_PENDING
