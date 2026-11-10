#!/usr/bin/env bash
# Build a dedicated local GGUF inference engine; no deletion and no system package upgrades.
set -Eeuo pipefail
R=/workspace/nox
D="$R/tools/llama.cpp"
BIN="$D/build/bin/llama-server"
mkdir -p "$R/tools" "$R/logs"
if command -v llama-server >/dev/null 2>&1 || [ -x "$BIN" ]; then
 echo NOX_LLAMA_CLI_AVAILABLE
 exit 0
fi
for prog in git cmake c++; do
 if ! command -v "$prog" >/dev/null 2>&1; then
  echo "HOLD_LLAMA_BUILD_DEPENDENCY_MISSING:$prog";exit 2
 fi
done
if [ ! -d "$D/.git" ]; then
 if [ -e "$D" ]; then echo HOLD_LLAMA_SOURCE_PATH_OCCUPIED;exit 2;fi
 git clone --depth 1 https://github.com/ggml-org/llama.cpp.git "$D"
fi
cd "$D"
if command -v nvcc >/dev/null 2>&1; then
 cmake -S . -B build -DGGML_CUDA=ON -DCMAKE_BUILD_TYPE=Release
else
 # CPU fallback keeps provenance correct, but does not claim 90% GPU throughput.
 echo NOX_LLAMA_GPU_TOOLCHAIN_UNAVAILABLE_USING_CPU_FALLBACK
 cmake -S . -B build -DGGML_CUDA=OFF -DCMAKE_BUILD_TYPE=Release
fi
cmake --build build --target llama-server llama-cli -j 2
test -x "$BIN" || { echo HOLD_LLAMA_CLI_NOT_BUILT; exit 2; }
echo "NOX_LLAMA_CLI_READY $BIN"
