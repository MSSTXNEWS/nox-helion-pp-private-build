#!/bin/bash
# T2.2: llama-server GLM-5.3 через mmap (без --no-mmap/--mlock). Эксперты на CPU, внимание на GPU.
pkill -f "llama-server" 2>/dev/null; sleep 1
L=$(dirname $(find /usr/local /usr/lib -name "libcublas.so.12" 2>/dev/null | head -1)); echo "cublas dir: $L"; export LD_LIBRARY_PATH=$L:/usr/local/cuda/lib64:/root/nox/llama.cpp/build/bin:$LD_LIBRARY_PATH; echo "$L" > /etc/ld.so.conf.d/nox-cuda.conf; ldconfig
M=/root/nox/glm53/GLM-5.3-UD-Q4_K_XL-00001-of-00011.gguf; BIN=/root/nox/llama.cpp/build/bin/llama-server
[ -x $BIN ] || { echo "no binary"; ls /root/nox/llama.cpp/build/bin | head; exit 1; }
LD_LIBRARY_PATH=$LD_LIBRARY_PATH nohup setsid $BIN -m $M --host 127.0.0.1 --port 8081 -c 16384 -t 24 -tb 24 -ngl 99 --n-cpu-moe 999 -fa on --parallel 1 --jinja --temp 1.0 --top-p 0.95 --min-p 0.01 > /root/nox/logs/glm_server.log 2>&1 < /dev/null &
for i in $(seq 1 60); do sleep 4; curl -fs http://127.0.0.1:8081/health >/dev/null 2>&1 && { echo "HEALTH OK after $((i*4))s"; break; }; done
tail -n 25 /root/nox/logs/glm_server.log | cut -c1-200; free -g | head -2
