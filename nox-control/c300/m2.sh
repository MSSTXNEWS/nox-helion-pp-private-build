#!/bin/bash
pkill -f glm_watch.sh; M=/dev/shm/glm53f/GLM-5.3-Flash-UD-Q4_K_XL-00001-of-00006.gguf; B=/root/nox/llama.cpp-g/build/bin/llama-server
pkill -9 -f 'llama-server.*--port 8081'; sleep 3
GGML_CUDA_NO_PINNED=1 timeout 120 nice -n 19 taskset -c 0-23 $B -m $M --host 127.0.0.1 --port 8081 --parallel 2 -c 16384 -fa on --jinja -ot exps=CPU --reasoning off --no-op-offload -ub 512 -b 2048 -ngl 36 -t 24 -tb 24 --spec-type draft-mtp --spec-draft-n-max 2 > /tmp/mtp_try.log 2>&1 &
sleep 45; grep -iE " E |error|mtp|nextn|draft|out of memory|not support" /tmp/mtp_try.log | head -12 | cut -c1-200
curl -s -m3 127.0.0.1:8081/health; echo
