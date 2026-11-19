#!/usr/bin/env bash
# NOX primary A40: CUDA-only llama server compiler, without changing host GPU driver.
set -Eeuo pipefail
D=/opt/nox_primary_llama/llama.cpp
BIN="$D/build/bin/llama-server"
mkdir -p /opt/nox_primary_llama /workspace/nox/logs
exec 9>/opt/nox_primary_llama/build.lock
flock -n 9 || { echo HOLD_CUDA_BUILD_ALREADY_RUNNING;exit 2; }
if [ -x "$BIN" ];then echo CUDA_LLAMA_READY;exit 0;fi
export PATH="/usr/local/cuda-12.8/bin:/usr/local/cuda/bin:$PATH"
if ! command -v nvcc >/dev/null 2>&1;then
 if [ "$(id -u)" != 0 ];then echo HOLD_ROOT_NEEDED;exit 2;fi
 df -Pk / | awk 'NR==2{if($4<12*1024*1024)exit 3}' || { echo HOLD_CUDA_TOOLKIT_NEEDS_DISK;exit 2; }
 if ! grep -q '^VERSION_ID="24.04"' /etc/os-release;then echo HOLD_UNSUPPORTED_OS;exit 2;fi
 curl -fsSL --retry 3 https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb -o /tmp/nox_cuda_keyring.deb
 dpkg -i /tmp/nox_cuda_keyring.deb
 DEBIAN_FRONTEND=noninteractive apt-get update -qq
 DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends cuda-toolkit-12-8
fi
for prog in git cmake c++ nvcc;do command -v "$prog" >/dev/null || { echo "HOLD_MISSING_$prog";exit 2; };done
if [ ! -d "$D/.git" ];then git clone --depth 1 https://github.com/ggml-org/llama.cpp.git "$D";fi
cmake -S "$D" -B "$D/build" -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release -DCMAKE_CUDA_COMPILER="$(command -v nvcc)"
cmake --build "$D/build" --target llama-server -j 3
test -x "$BIN" || { echo HOLD_GPU_BINARY_NOT_BUILT;exit 2; }
echo NOX_A40_SOLO_CUDA_READY
