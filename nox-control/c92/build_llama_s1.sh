#!/bin/bash
# T1.3: сборка llama.cpp master (CUDA sm_120), фон, лог в /root/nox/logs/build_llama.log
mkdir -p /root/nox/logs; exec 9>/root/nox/logs/build.lock; flock -n 9 || { echo running; tail -3 /root/nox/logs/build_llama.log; exit 0; }
cat > /root/nox/build_llama_worker.sh <<'W'
set -x
cd /root/nox
[ -d llama.cpp ] || git clone --depth 1 https://github.com/ggml-org/llama.cpp
cd llama.cpp && git log -1 --format=%H
export PATH=/usr/local/cuda/bin:$PATH
cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=120 -DGGML_NATIVE=ON -DGGML_CUDA_FA=ON -DGGML_CUDA_GRAPHS=ON -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -15
cmake --build build -j 20 --target llama-server llama-cli llama-bench 2>&1 | tail -30
ls -la build/bin | head; echo BUILD_DONE $(date)
W
nohup setsid bash -c 'exec 9>&-; bash /root/nox/build_llama_worker.sh' > /root/nox/logs/build_llama.log 2>&1 < /dev/null &
sleep 15; tail -5 /root/nox/logs/build_llama.log
echo "== dl"; tail -c 300 /root/nox/logs/glm_dl.log | tr '\r' '\n' | tail -3; du -sh /dev/shm/nox_glm /root/nox/glm53_disk 2>/dev/null; df -h /dev/shm | tail -1
