#!/bin/bash
cp /root/nox/start_glm.sh /root/nox/start_glm.sh.c320_$(date +%H%M)
cat > /root/nox/start_glm.sh <<'S'
#!/bin/bash
# c300: лучший замер (flash_ab4): tg 5.73. Ядра 26-33 оставлены быстрой модели.
pkill -9 -f 'llama-server.*--port 8081'; sleep 3
GGML_CUDA_NO_PINNED=1 nohup nice -n 19 taskset -c 0-23 /root/nox/llama.cpp-f/build/bin/llama-server -m /dev/shm/glm53f/GLM-5.3-Flash-UD-Q4_K_XL-00001-of-00006.gguf --host 127.0.0.1 --port 8081 --parallel 2 -c 16384 -fa on --jinja -ot exps=CPU --reasoning off --no-op-offload -ub 512 -b 2048 -ngl 40 -t 24 -tb 24 > /root/nox/logs/glm_8081.log 2>&1 &
S
bash /root/nox/start_glm.sh; for i in $(seq 60); do sleep 3; curl -sf -m2 127.0.0.1:8081/health >/dev/null && break; done; echo "glm up ${i}x3"
python3 - <<'P'
import json,urllib.request,time
def t(url,body):
    s=time.time(); r=json.load(urllib.request.urlopen(urllib.request.Request(url,json.dumps(body).encode(),{"Content-Type":"application/json"}),timeout=200)); return time.time()-s, r
d,r=t("http://127.0.0.1:8081/v1/chat/completions",{"messages":[{"role":"user","content":"Расскажи коротко про Луну."}],"max_tokens":120,"temperature":0}); print("GLM tg %.2f"%r["timings"]["predicted_per_second"])
d,r=t("http://127.0.0.1:8083/v1/chat/completions",{"messages":[{"role":"user","content":"Привет, как ты?"}],"max_tokens":60}); print("8083 direct %.1fs"%d)
d,r=t("http://127.0.0.1:8082/v1/chat/completions",{"messages":[{"role":"user","content":"Привет, как ты?"}],"max_tokens":60,"stream":False}); print("gateway %.1fs"%d, json.dumps(r.get("nox",{}),ensure_ascii=False)[:600])
P
