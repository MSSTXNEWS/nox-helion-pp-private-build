#!/bin/bash
N=/workspace/nox; S=$N/state/p3; D=$(date +%Y%m%d_%H%M%S)
echo "== clients of 8104 now (client-side sockets)"
for i in 1 2 3; do ss -Htnp state established '( dport = :8104 )' | grep -o 'users:(("[^"]*",pid=[0-9]*' | sort | uniq -c; echo --; sleep 3; done
for pid in $(ss -Htnp state established '( dport = :8104 )' | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u); do echo "pid $pid age=$(ps -o etimes= -p $pid)s $(tr '\0' ' ' </proc/$pid/cmdline | cut -c1-140)"; done
echo "== max_tokens 3500/2200/1800 in code"; grep -rIn --include=*.py -E "max_tokens['\"]?\s*[:=,]\s*(3500|2200|1800)|\b(3500|2200|1800)\b.*max_tok|max_tok.*\b(3500|2200|1800)\b" $N/agent $N/stewards $N/ops $N/brain $N/operators 2>/dev/null | grep -v -E "\.bak|/backup/" | cut -c1-200 | head -15
echo "== 8106 stop (reversible)"
P=$(pgrep -f "llama-server.*--port 8106" | head -1)
if [ -n "$P" ]; then tr '\0' '\n' </proc/$P/cmdline > $S/8106.cmd; cat > $S/start_8106.sh <<'EOS'
#!/bin/bash
# возврат 8106: nohup taskset BG-ядра nice 15
mapfile -t A < /workspace/nox/state/p3/8106.cmd
cd /workspace/nox; set -a; . /workspace/nox/agent/autotrain/donor.env 2>/dev/null; set +a
setsid nohup taskset -c 4-7,20-23 nice -n 15 "${A[@]}" > /workspace/nox/agent/out/p3_8106.log 2>&1 9>&- &
EOS
chmod +x $S/start_8106.sh; wc -l $S/8106.cmd
cp -p $N/state/dual_judge.json $S/dual_judge.json.bak_$D
python3 - <<'PY'
import json
p="/workspace/nox/state/dual_judge.json"; d=json.load(open(p)); n=len(d["judges"])
d["judges"]=[j for j in d["judges"] if j.get("name")!="gptoss"]; print("judges",n,"->",len(d["judges"]))
json.dump(d,open(p,"w"),ensure_ascii=False,indent=2)
PY
echo "before: $(grep -E 'MemAvailable' /proc/meminfo) state8104=$(ps -o stat= -p $(pgrep -f 'port 8104'|head -1))"
kill -TERM $P; sleep 5; kill -0 $P 2>/dev/null && echo "still alive" || echo "8106 stopped"
else echo "8106 not running"; fi
cat > /tmp/p3_after.sh <<'EOC'
#!/bin/bash
O=/workspace/nox/state/p3/after_8106.txt
{ for i in 1 2 3 4 5 6; do sleep 20; echo "t+$((i*20))s $(grep MemAvailable /proc/meminfo | awk '{print int($2/1024)"MB"}') st=$(ps -o stat= -p $(pgrep -f 'port 8104'|head -1)) $(vmstat 1 2 | tail -1 | awk '{print "bi="$9" wa="$16}') $(curl -s -m3 127.0.0.1:8104/slots | python3 -c "import sys,json;print(' '.join('%s'%s.get('next_token',[{}])[0].get('n_decoded') for s in json.load(sys.stdin)))")"; done
cat > /tmp/p3_t.py <<'PY'
import json,time,http.client
t=time.time()
try:
    c=http.client.HTTPConnection("127.0.0.1",8104,timeout=90)
    c.request("POST","/v1/chat/completions",json.dumps({"messages":[{"role":"user","content":"Расскажи в пяти предложениях о Севастополе."}],"max_tokens":100,"stream":True,"chat_template_kwargs":{"enable_thinking":False}}),{"Content-Type":"application/json"})
    r=c.getresponse();ft=None;n=0
    while True:
        l=r.readline()
        if not l:break
        if l.startswith(b"data:") and b'"content":"' in l and b'"content":""' not in l:
            n+=1
            if ft is None: ft=time.time()-t
    tt=time.time()-t; print("ttft_s",ft and round(ft,2),"total_s",round(tt,1),"tok_s",ft and n>1 and round((n-1)/(tt-ft),1))
except Exception as e: print("ERR",type(e).__name__)
PY
timeout 100 python3 /tmp/p3_t.py; echo DONE; } > $O 2>&1
EOC
chmod +x /tmp/p3_after.sh; nohup setsid /tmp/p3_after.sh >/dev/null 2>&1 &
echo started measure
