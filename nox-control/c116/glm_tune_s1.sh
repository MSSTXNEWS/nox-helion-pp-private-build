#!/bin/bash
# Установка профиля GLM-5.3: шлюз G01-G33 + A/B серверных флагов (G13 -b/-ub, G15 moe-cache). Фон: результат в /root/nox/logs/tune.log
exec 9>/root/nox/logs/tune.lock; flock -n 9 || { echo running; tail -20 /root/nox/logs/tune.log; exit 0; }
cat > /root/nox/tune_worker.sh <<'W'
export LD_LIBRARY_PATH=/usr/local/cuda-12.9/targets/x86_64-linux/lib:/root/nox/llama.cpp/build/bin
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/glm53; G=/root/nox/glm53gw; mkdir -p $G
for f in glm_profile.py gateway.py persona_short_ru.txt test_glm_profile.py; do curl -fsSL $R/$f -o $G/$f; done
python3 -m unittest $G/test_glm_profile.py 2>&1 | tail -3
M=/root/nox/glm53/GLM-5.3-UD-Q4_K_XL-00001-of-00011.gguf; BIN=/root/nox/llama.cpp/build/bin/llama-server
bench(){ python3 - <<'P'
import json,urllib.request
def q(p,n):
    r=urllib.request.Request("http://127.0.0.1:8081/completion",data=json.dumps({"prompt":p,"n_predict":n,"cache_prompt":False}).encode(),headers={"Content-Type":"application/json"})
    return json.loads(urllib.request.urlopen(r,timeout=900).read())["timings"]
long=("Нейросети на основе смеси экспертов активируют лишь часть параметров на каждый токен. "*45)+" Кратко:"
a=q(long,30); b=q("Расскажи коротко о Python.",100); c=q("Расскажи коротко о Linux.",100)
print("  prompt(%d tok) %.1f t/s | gen %.2f / %.2f t/s"%(a["prompt_n"],a["prompt_per_second"],b["predicted_per_second"],c["predicted_per_second"]))
P
}
start(){ pkill -f "llama-server -m"; sleep 3
 nohup setsid $BIN -m $M --host 127.0.0.1 --port 8081 -c 16384 -t 24 -tb 24 -fa on --parallel 1 --jinja --temp 1.0 --top-p 0.95 --min-p 0.01 --n-cpu-moe 999 "$@" > /root/nox/logs/glm_server.log 2>&1 < /dev/null &
 for i in $(seq 1 150); do sleep 4; curl -fs http://127.0.0.1:8081/health >/dev/null 2>&1 && return 0; done; echo "NOT HEALTHY"; grep -E " E " /root/nox/logs/glm_server.log | tail -3; return 1; }
echo "== A: ngl44 b4096 ub4096 (G13)"; start -ngl 44 -b 4096 -ub 4096 && bench
echo "== B: ngl34 b4096 ub4096 moe-cache 4000 (G15)"; start -ngl 34 -b 4096 -ub 4096 --moe-cache-mib 4000 && bench; nvidia-smi --query-gpu=memory.used --format=csv,noheader
echo "== C: ngl30 b4096 ub4096 moe-cache 7000"; start -ngl 30 -b 4096 -ub 4096 --moe-cache-mib 7000 && bench; nvidia-smi --query-gpu=memory.used --format=csv,noheader
echo TUNE_DONE $(date)
W
nohup setsid bash -c 'exec 9>&-; bash /root/nox/tune_worker.sh' > /root/nox/logs/tune.log 2>&1 < /dev/null &
sleep 5; cat /root/nox/logs/tune.log
