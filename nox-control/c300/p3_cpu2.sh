#!/bin/bash
# P3 cpu2: kill stuck QA chrome (>2h), pin cores: CHAT 8-15,24-31 | TRAIN 0-3,16-19 | BG 4-7,20-23; enforcer loop. Backup of affinities.
S=/workspace/nox/state; mkdir -p $S/p3; B=$S/p3/cpu_backup_$(date +%Y%m%d_%H%M%S).txt
CHAT="8-15,24-31"; TRAIN="0-3,16-19"; BG="4-7,20-23"
snap(){ echo "load $(cut -d' ' -f1-3 /proc/loadavg) idle $(top -bn2 -d3 | grep Cpu | tail -1 | sed 's/.*ni, *\([0-9.]*\) id.*/\1/')%"; }
echo "BEFORE $(snap)"
echo "== chat_priority_guard head"; sed -n 1,40p /workspace/nox/ops/chat_priority_guard.sh | cut -c1-180
# backup current state of processes we will touch
{ for p in $(pgrep -f "llama-server|judge_service|embed_server|distill_v2|compile_worker|web_server.py|nox_core.py|chrome-headless|playwright|qa_audit|qa_ctl|nox_index.py|meilisearch"); do echo "$p aff=$(taskset -cp $p 2>/dev/null|sed 's/.*: //') ni=$(ps -o ni= -p $p|tr -d ' ') :: $(tr '\0' ' ' </proc/$p/cmdline | cut -c1-80)"; done; } > $B; echo "backup $B $(wc -l <$B) procs; restore: taskset -a -cp 0-31 PID; renice 0 PID"
# 1) stuck QA chrome/playwright older than 2h (etimes>7200), whitelist by exe path only
for p in $(pgrep -f "ms-playwright|playwright/driver"); do e=$(ps -o etimes= -p $p|tr -d ' '); [ "${e:-0}" -gt 7200 ] && echo $p; done > /tmp/p3_stuck.txt
echo "stuck QA procs: $(wc -l </tmp/p3_stuck.txt)"; for p in $(cat /tmp/p3_stuck.txt); do ps -o ppid= -p $p; done | sort -u | while read pp; do echo "parent $pp: $(tr '\0' ' ' </proc/$pp/cmdline 2>/dev/null | cut -c1-120)"; done
for p in $(cat /tmp/p3_stuck.txt); do kill -TERM $p 2>/dev/null; done; sleep 3; for p in $(cat /tmp/p3_stuck.txt); do kill -0 $p 2>/dev/null && kill -KILL $p; done
echo "chrome left: $(pgrep -fc chrome-headless)"
# 2) enforcer
cat > /workspace/nox/ops/p3_cpuset_guard.sh <<'EOG'
#!/bin/bash
# P3: стандартные taskset/renice; чат — выделенные ядра, остальное — свои. Цикл 60 с. Откат: pkill -f p3_cpuset_guard; taskset -a -cp 0-31 PID
CHAT="8-15,24-31"; TRAIN="0-3,16-19"; BG="4-7,20-23"
pin(){ c=$1; n=$2; shift 2; for pat in "$@"; do for p in $(pgrep -f "$pat"); do [ "$p" = "$$" ] && continue; taskset -a -cp $c $p >/dev/null 2>&1; renice -n $n -p $p >/dev/null 2>&1; done; done; }
while true; do
  pin $CHAT -5 "llama-server.*--port 8104" "python web_server.py" "nox_core.py" "llama-swap"
  pin $TRAIN 0 "distill_v2.py train" "torch/_inductor/compile_worker"
  pin $BG 10 "judge_service:app" "embed_server.py" "llama-server.*--port (8106|8141|8142|8143|8151|8152|8811|8812)" "qa_audit.py" "qa_ctl.py" "chrome-headless-shell" "playwright/driver" "nox_index.py" "meilisearch"
  sleep 60
done
EOG
chmod +x /workspace/nox/ops/p3_cpuset_guard.sh
[ -f $S/p3/guard.pid ] && kill $(cat $S/p3/guard.pid) 2>/dev/null
nohup setsid /workspace/nox/ops/p3_cpuset_guard.sh >/dev/null 2>&1 & echo $! > $S/p3/guard.pid
sleep 45
echo "== after pin"; for pat in "port 8104" "judge_service:app" "distill_v2.py train" "port 8106" "web_server.py"; do p=$(pgrep -f "$pat"|head -1); echo "$pat pid $p aff=$(taskset -cp $p|sed 's/.*: //') ni=$(ps -o ni= -p $p)"; done
sleep 30; echo "AFTER $(snap)"
python3 - <<'PY'
import json,time,http.client
for q in ("Привет, расскажи кратко о Севастополе.","Назови столицу Франции."):
    t=time.time();c=http.client.HTTPConnection("127.0.0.1",8104,timeout=120)
    c.request("POST","/v1/chat/completions",json.dumps({"messages":[{"role":"user","content":q}],"max_tokens":80,"stream":True}),{"Content-Type":"application/json"})
    r=c.getresponse();ft=None;n=0
    while True:
        l=r.readline()
        if not l:break
        if l.startswith(b"data:") and b'"delta"' in l and (b'"content":"' in l or b'"reasoning_content":"' in l) and b'"content":""' not in l:
            n+=1
            if ft is None: ft=time.time()-t
    print("8104 first_token_s",ft and round(ft,2),"total_s",round(time.time()-t,1),"chunks",n)
PY
