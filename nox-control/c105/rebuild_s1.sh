#!/bin/bash
# cuBLAS dev из репозитория NVIDIA (apt), затем пересборка llama.cpp (фон)
export DEBIAN_FRONTEND=noninteractive
(apt-get update -qq 2>&1 | tail -2; apt-get install -y -qq libcublas-dev-12-9 2>&1 | tail -3)
ls /usr/local/cuda/include/cublas_v2.h /usr/local/cuda/lib64/libcublas.so 2>&1
exec 9>/root/nox/logs/build.lock; flock -n 9 || { echo running; exit 0; }
cat > /root/nox/build_llama_worker.sh <<'W'
set -x
cd /root/nox/llama.cpp && rm -rf build
export PATH=/usr/local/cuda/bin:$PATH
cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=120 -DGGML_NATIVE=ON -DGGML_CUDA_FA=ON -DGGML_CUDA_GRAPHS=ON -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -8
cmake --build build -j 24 --target llama-server llama-cli llama-bench 2>&1 | tail -12
ls build/bin | grep -E "^llama-" ; echo BUILD_DONE $(date)
W
nohup setsid bash -c 'exec 9>&-; bash /root/nox/build_llama_worker.sh' > /root/nox/logs/build_llama.log 2>&1 < /dev/null &
sleep 30; tail -n 6 /root/nox/logs/build_llama.log | cut -c1-180
