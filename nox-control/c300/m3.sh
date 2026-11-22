#!/bin/bash
cat > /root/nox/mtp_ab2.sh <<'X'
#!/bin/bash
L=/root/nox/logs/mtp_ab2.log; : > $L; pkill -f glm_watch.sh
M=/dev/shm/glm53f/GLM-5.3-Flash-UD-Q4_K_XL-00001-of-00006.gguf; BIN=/root/nox/llama.cpp-g/build/bin/llama-server
BASE="--host 127.0.0.1 --port 8081 --parallel 2 -c 16384 -fa on --jinja -ot exps=CPU --reasoning off --no-op-offload -ub 512 -b 2048 -t 24 -tb 24"
run() { pkill -9 -f 'llama-server.*--port 8081'; sleep 3
  GGML_CUDA_NO_PINNED=1 nohup nice -n 19 taskset -c 0-23 $BIN -m $M $BASE $1 > /root/nox/logs/glm_8081.log 2>&1 &
  for i in $(seq 80); do sleep 3; curl -sf -m2 127.0.0.1:8081/health >/dev/null && break; pgrep -f 'port 8081' >/dev/null || break; done
  curl -sf -m2 127.0.0.1:8081/health >/dev/null || { echo "$2 FAILED" >> $L; return; }
  python3 - "$2" "$1" >> $L <<'P'
import json,urllib.request,sys
q=["Объясни подробно, как работает память человека и почему мы забываем.","Напиши короткий план, как ускорить сервер с ИИ: шаги по порядку.","Привет! Как настроение?"]
tg=[]
for x in q:
    b={"messages":[{"role":"user","content":x}],"max_tokens":160,"temperature":0.7,"cache_prompt":False}
    r=json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8081/v1/chat/completions",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=900))
    t=r["timings"]; tg.append(t["predicted_per_second"]); acc=(t.get("draft_n_accepted"),t.get("draft_n"))
print(sys.argv[1],"avg %.2f"%(sum(tg)/len(tg)),["%.2f"%x for x in tg],"acc",acc,"|",sys.argv[2])
P
}
run "-ngl 40" "NGL40"
run "-ngl 36 --spec-type draft-mtp --spec-draft-n-max 2" "MTP2_ngl36"
run "-ngl 36 --spec-type draft-mtp --spec-draft-n-max 3" "MTP3_ngl36"
run "-ngl 38 --spec-type draft-mtp --spec-draft-n-max 2" "MTP2_ngl38"
python3 - >> $L <<'P'
import re
rows=[(m.group(1),float(m.group(2)),m.group(3)) for l in open("/root/nox/logs/mtp_ab2.log") for m in [re.match(r"(\S+) avg ([\d.]+) .*\| (.*)",l)] if m]
best=max(rows,key=lambda r:r[1]); print("BEST",best[0],best[1]); open("/tmp/mtp2_best","w").write(best[2])
P
X=$(cat /tmp/mtp2_best)
cat > /root/nox/start_glm.sh <<S
#!/bin/bash
# c300 W061: автоподбор mtp_ab2. Ядра 26-33 оставлены быстрой модели.
pkill -9 -f 'llama-server.*--port 8081'; sleep 3
GGML_CUDA_NO_PINNED=1 nohup nice -n 19 taskset -c 0-23 $BIN -m $M $BASE $X > /root/nox/logs/glm_8081.log 2>&1 &
S
bash /root/nox/start_glm.sh; sleep 40; (nohup setsid bash /root/nox/glm_watch.sh >/dev/null 2>&1 </dev/null &)
echo "DONE health=$(curl -s -m3 -o /dev/null -w %{http_code} 127.0.0.1:8081/health)" >> $L
X
(nohup setsid bash /root/nox/mtp_ab2.sh >/dev/null 2>&1 </dev/null &); echo started
