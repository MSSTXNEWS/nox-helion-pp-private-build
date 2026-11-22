#!/bin/bash
# W061-W064: свежий llama.cpp + MTP A/B. Лог: /root/nox/logs/mtp_ab.log
L=/root/nox/logs/mtp_ab.log; echo "$(date -u +%T) start" > $L
cd /root/nox && rm -rf llama.cpp-g && git clone -q --depth 1 https://github.com/ggml-org/llama.cpp llama.cpp-g && cd llama.cpp-g && echo "commit $(git log -1 --format='%h %cd' --date=short)" >> $L
grep -rl "nextn\|NEXTN" src/ 2>/dev/null | head -3 >> $L; grep -c "GLM5_NEXT\|glm5next" src/llama-arch.cpp >> $L
cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=120 -DLLAMA_CURL=OFF -DBUILD_SHARED_LIBS=OFF > ../logs/mtp_build.log 2>&1 && nice -n 15 taskset -c 34-55 cmake --build build -j 20 --target llama-server >> ../logs/mtp_build.log 2>&1 && echo "built" >> $L || { echo "BUILD FAIL"; tail -5 ../logs/mtp_build.log; } >> $L
[ -x /root/nox/llama.cpp-g/build/bin/llama-server ] || exit 0
pkill -f glm_watch.sh
M=/dev/shm/glm53f/GLM-5.3-Flash-UD-Q4_K_XL-00001-of-00006.gguf
BASE="--host 127.0.0.1 --port 8081 --parallel 2 -c 16384 -fa on --jinja -ot exps=CPU --reasoning off --no-op-offload -ub 512 -b 2048 -ngl 40 -t 24 -tb 24"
run() { pkill -9 -f 'llama-server.*--port 8081'; sleep 3
  GGML_CUDA_NO_PINNED=1 nohup nice -n 19 taskset -c 0-23 $1 -m $M $BASE $2 > /root/nox/logs/glm_8081.log 2>&1 &
  for i in $(seq 80); do sleep 3; curl -sf -m2 127.0.0.1:8081/health >/dev/null && break; pgrep -f 'port 8081' >/dev/null || break; done
  curl -sf -m2 127.0.0.1:8081/health >/dev/null || { echo "$3 FAILED: $(grep -iE 'error|unknown|invalid' /root/nox/logs/glm_8081.log | head -2 | cut -c1-160)" >> $L; return; }
  python3 - "$3" >> $L <<'P'
import json,urllib.request,sys
q=["Объясни подробно, как работает память человека и почему мы забываем.","Напиши короткий план, как ускорить сервер с ИИ: шаги по порядку."]
tg=[]
for x in q:
    b={"messages":[{"role":"user","content":x}],"max_tokens":160,"temperature":0.7,"cache_prompt":False}
    r=json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8081/v1/chat/completions",json.dumps(b).encode(),{"Content-Type":"application/json"}),timeout=900))
    t=r["timings"]; tg.append(t["predicted_per_second"]); acc=t.get("draft_n_accepted"),t.get("draft_n")
print(sys.argv[1],"tg %.2f / %.2f"%tuple(tg),"draft acc",acc)
P
}
run /root/nox/llama.cpp-f/build/bin/llama-server "" "OLD"
run /root/nox/llama.cpp-g/build/bin/llama-server "" "NEW"
run /root/nox/llama.cpp-g/build/bin/llama-server "--spec-type draft-mtp --spec-draft-n-max 2" "NEW+MTP2"
run /root/nox/llama.cpp-g/build/bin/llama-server "--spec-type draft-mtp --spec-draft-n-max 3" "NEW+MTP3"
python3 - >> $L <<'P'
import re
best=None
for l in open("/root/nox/logs/mtp_ab.log"):
    m=re.match(r"(\S+) tg ([\d.]+) / ([\d.]+)",l)
    if m:
        v=(float(m.group(2))+float(m.group(3)))/2
        if not best or v>best[1]*1.05 or (best[0]=="OLD" and v>best[1]): best=(m.group(1),v)
print("BEST",best)
open("/tmp/mtp_best","w").write(best[0])
P
B=$(cat /tmp/mtp_best)
case $B in OLD) BIN=/root/nox/llama.cpp-f/build/bin/llama-server; X="";; NEW) BIN=/root/nox/llama.cpp-g/build/bin/llama-server; X="";; NEW+MTP2) BIN=/root/nox/llama.cpp-g/build/bin/llama-server; X="--spec-type draft-mtp --spec-draft-n-max 2";; *) BIN=/root/nox/llama.cpp-g/build/bin/llama-server; X="--spec-type draft-mtp --spec-draft-n-max 3";; esac
cat > /root/nox/start_glm.sh <<S
#!/bin/bash
# c300 W061: автоподбор mtp_ab ($B). Ядра 26-33 оставлены быстрой модели.
pkill -9 -f 'llama-server.*--port 8081'; sleep 3
GGML_CUDA_NO_PINNED=1 nohup nice -n 19 taskset -c 0-23 $BIN -m $M $BASE $X > /root/nox/logs/glm_8081.log 2>&1 &
S
bash /root/nox/start_glm.sh; sleep 40; (nohup setsid bash /root/nox/glm_watch.sh >/dev/null 2>&1 </dev/null &)
echo "DONE $(date -u +%T) health=$(curl -s -m3 -o /dev/null -w %{http_code} 127.0.0.1:8081/health)" >> $L
