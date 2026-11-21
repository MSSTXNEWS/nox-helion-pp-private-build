#!/bin/bash
# c53: проверка NOX (диск, GPU, службы, задачи) + перезапуск модели и тест чата. STOP-флаг уважается для обучения, не для проверки.
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-200; }
echo "== time"; date -Is
echo "== disk"; df -h / /root /workspace 2>/dev/null | a; du -sh /root/nox/models /root/nox/lora /root/nox/state /root/nox/logs /root/.cache /tmp 2>/dev/null | sort -rh | a
echo "== gpu"; nvidia-smi --query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu --format=csv,noheader
echo "== mem"; free -m | sed -n 2p
echo "== supervisor"; supervisorctl status | awk '{print $1,$2}' | a
echo "== health BEFORE"; curl -s -m5 127.0.0.1:8098/health | head -c 120; echo; curl -s -m5 127.0.0.1:8091/api/health | head -c 200 | a; echo
echo "== STOP flags"; ls /root/nox/STOP* /root/nox/state/STOP* 2>&1 | head -3
echo "== tasks files"; ls -la /root/nox/state/*task* /root/nox/*.json 2>/dev/null | awk '{print $5,$9}' | head -12
for f in /root/nox/state/work_tasks.json /root/nox/state/tasks.json /root/nox/state/task_queue.json; do [ -f $f ] && { echo "-- $f"; /root/nox/venv/bin/python - "$f" <<'PY'
import json,sys,collections
d=json.load(open(sys.argv[1]));L=d.get("tasks",d) if isinstance(d,dict) else d
c=collections.Counter(str(t.get("status")) for t in L if isinstance(t,dict));print("total",len(L),dict(c))
for t in [t for t in L if isinstance(t,dict) and str(t.get("status")).lower() not in ("done","completed","closed")][:15]:
    print(" ",t.get("id"),str(t.get("status")),str(t.get("title") or t.get("goal") or "")[:80])
PY
}; done
echo "== training"; supervisorctl status | grep -iE "train|distill|lora|learn|knowledge" | awk '{print $1,$2}'; ls -t /root/nox/logs | head -5; tail -n 3 $(ls -t /root/nox/logs/*train* 2>/dev/null | head -1) 2>/dev/null | a
echo "== drive"; ls /root/nox/state | grep -i drive | head; tail -n 3 $(ls -t /root/nox/logs/*drive* 2>/dev/null | head -1) 2>/dev/null | a; df -h 2>/dev/null | grep -iE "drive|fuse|rclone" | a; which rclone >/dev/null && rclone listremotes 2>&1 | head -3
echo "== RESTART model"
supervisorctl restart nox-ds41-8098 2>&1 | tail -1
ok=0; for i in $(seq 1 60); do curl -s -m3 127.0.0.1:8098/health | grep -q ok && { ok=1; break; }; sleep 10; done; echo "model up=$ok after $((i*10))s"
supervisorctl restart nox-bridge 2>&1 | tail -1; sleep 15
echo "== health AFTER"; curl -s -m5 127.0.0.1:8098/health | head -c 120; echo; curl -s -m5 127.0.0.1:8091/api/health | head -c 300 | a; echo
echo "== chat test"; /root/nox/venv/bin/python /dev/stdin <<'PY' 2>&1 | a
import json,sys,urllib.request
sys.path.insert(0,"/root/nox/scripts")
try:
    from common import read_api_key; key=read_api_key()
    b={"model":"deepseek-v41-flash-iq2xxs","stream":False,"max_tokens":80,"messages":[{"role":"user","content":"Кто ты? Ответь одной фразой."}]}
    r=urllib.request.Request("http://127.0.0.1:8080/v1/chat/completions",data=json.dumps(b).encode(),headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"})
    print(urllib.request.urlopen(r,timeout=180).read().decode()[:500].replace(key,"***"))
except Exception as e: print("chat FAIL",type(e).__name__,str(e)[:150])
PY
echo "== supervisor AFTER (not RUNNING)"; supervisorctl status | grep -v RUNNING | awk '{print $1,$2}' | a
echo done
