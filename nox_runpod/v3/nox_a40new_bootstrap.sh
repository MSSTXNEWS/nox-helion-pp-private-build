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
 # CUDA runtime in PyTorch image is not the CUDA compiler; install toolkit,
 # without replacing NVIDIA host drivers. Never install package 'cuda' (includes drivers).
 if ! command -v nvcc >/dev/null 2>&1 && [ ! -x /usr/local/cuda-12.8/bin/nvcc ];then
  echo NOX_INSTALL_CUDA_12_8_COMPILER_ONLY
  test "$(id -u)" = 0 || { echo HOLD_ROOT_REQUIRED_FOR_CUDA_TOOLKIT;exit 3; }
  df -Pk / | awk 'NR==2 {if ($4 < 15*1024*1024)exit 3}' || { echo HOLD_DISK_NEED_15_GIB_FOR_CUDA_TOOLKIT;exit 3; }
  if [ ! -f /etc/os-release ] || ! grep -q '^VERSION_ID="24.04"' /etc/os-release;then
   echo HOLD_CUDA_INSTALL_UNSUPPORTED_UBUNTU_VERSION;exit 3
  fi
  curl -fsSL --retry 3 'https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb' -o /tmp/nox_cuda_keyring.deb
  dpkg -i /tmp/nox_cuda_keyring.deb
  DEBIAN_FRONTEND=noninteractive apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends cuda-toolkit-12-8
 fi
 export PATH="/usr/local/cuda-12.8/bin:/usr/local/cuda/bin:$PATH"
 command -v nvcc >/dev/null 2>&1 || { echo HOLD_CUDA_COMPILER_STILL_MISSING;exit 3; }
 echo "NOX_CUDA_COMPILER $(nvcc --version | tail -n 1)"
 for dep in git cmake c++;do command -v "$dep" >/dev/null 2>&1 || { echo "HOLD_MISSING_$dep";exit 3; };done
 if [ ! -d "$D/.git" ];then
  mkdir -p /opt/nox_a40new
  git clone --depth 1 https://github.com/ggml-org/llama.cpp.git "$D"
 fi
 cmake -S "$D" -B "$D/build" -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_COMPILER="$(command -v nvcc)"
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
