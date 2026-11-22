#!/bin/bash
# GLM-5.3-Flash: отключить перегон экспертов по PCIe при чтении запроса (--no-op-offload), замер
cat > /root/nox/start_glm.sh <<'S'
#!/bin/bash
pkill -f 'llama-server.*--port 8081'; sleep 5
GGML_CUDA_NO_PINNED=1 nohup nice -n 5 /root/nox/llama.cpp-f/build/bin/llama-server -m /dev/shm/glm53f/GLM-5.3-Flash-UD-Q4_K_XL-00001-of-00006.gguf --host 127.0.0.1 --port 8081 --parallel 1 -c 16384 -fa on --jinja -ngl 24 -ot exps=CPU --no-op-offload -t 26 -tb 26 -ub 512 -b 2048 > /root/nox/logs/glm_8081.log 2>&1 &
S
chmod +x /root/nox/start_glm.sh
cat > /root/nox/flash_ab.sh <<'S'
#!/bin/bash
bash /root/nox/start_glm.sh
for i in $(seq 120); do sleep 5; curl -sf -m 2 127.0.0.1:8081/health >/dev/null && break; done
echo "up after $((i*5))s" > /root/nox/logs/flash_ab.log
python3 - >> /root/nox/logs/flash_ab.log 2>&1 <<'P'
import json,urllib.request,time
txt=open("/root/nox/canon_v5.txt",encoding="utf-8").read()[:2500]
b={"prompt":"Кратко перескажи:\n"+txt+"\nПересказ:","n_predict":80,"cache_prompt":False}
t=time.time();r=json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8081/completion",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=1800))
tm=r["timings"];print("pp %.2f t/s (%d tok) tg %.2f t/s wall %.0fs"%(tm["prompt_per_second"],tm["prompt_n"],tm["predicted_per_second"],time.time()-t))
P
grep -iE "op.offload|offloaded" /root/nox/logs/glm_8081.log | head -3 >> /root/nox/logs/flash_ab.log
S
nohup setsid bash /root/nox/flash_ab.sh >/dev/null 2>&1 < /dev/null &
echo started
