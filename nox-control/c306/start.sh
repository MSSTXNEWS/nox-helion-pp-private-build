#!/bin/bash
# ждём конца flash.py (до 8 мин), затем свой один запуск Flash на 8081
for i in $(seq 1 48); do pgrep -f "python3 flash.py" >/dev/null || break; sleep 10; done
pgrep -f "python3 flash.py" >/dev/null && { echo "flash.py ещё жив, не запускаю"; tail -n 2 /root/nox/logs/flash.log|cut -c1-150; exit 0; }
tail -n 2 /root/nox/logs/flash.log | cut -c1-150
curl -sf -m 3 http://127.0.0.1:8081/health && { echo "уже стоит"; exit 0; }
M=/dev/shm/glm53f/GLM-5.3-Flash-UD-Q4_K_XL-00001-of-00006.gguf
B=/root/nox/llama.cpp-f/build/bin/llama-server
export LD_LIBRARY_PATH=/usr/local/cuda-12.9/targets/x86_64-linux/lib:$LD_LIBRARY_PATH
try() { # $1 имя, остальное - доп. аргументы
  n=$1; shift; echo "=== try $n $*"; pkill -f "llama-server.*--port 8081"; sleep 3
  GGML_CUDA_NO_PINNED=1 nohup setsid $B -m $M --host 127.0.0.1 --port 8081 --parallel 4 -c 32768 -fa on --jinja -ngl 99 -ot "exps=CPU" -t 26 -tb 26 "$@" > /root/nox/logs/glm_8081.log 2>&1 < /dev/null &
  echo "$B -m $M --host 127.0.0.1 --port 8081 --parallel 4 -c 32768 -fa on --jinja -ngl 99 -ot exps=CPU -t 26 -tb 26 $*" > /root/nox/state/FLASH_ARGS_$n.txt
  for j in $(seq 1 100); do
    [ "$(curl -s -m 3 -o /dev/null -w '%{http_code}' http://127.0.0.1:8081/health)" = 200 ] && { echo "UP try=$n after $((j*5))s"; echo $n > /root/nox/state/FLASH_ARGS_USED; return 0; }
    pgrep -f "port 8081" >/dev/null || { echo "DIED try=$n"; grep -a -E "alloc|failed to" /root/nox/logs/glm_8081.log | tail -n 3 | cut -c1-200; return 1; }
    sleep 5
  done; echo TIMEOUT; return 1; }
try C -ub 256 -b 1024 || try D -ub 128 -b 512 || try E -ub 128 -b 512 -ngl 24
nvidia-smi --query-gpu=memory.used --format=csv,noheader
grep -a -E "buffer size|KV|offloaded|model buffer" /root/nox/logs/glm_8081.log | cut -c1-200 | head -8
