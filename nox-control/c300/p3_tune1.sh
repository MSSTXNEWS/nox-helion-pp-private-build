#!/bin/bash
N=/workspace/nox; S=$N/state/p3; mkdir -p $S; D=$(date +%Y%m%d_%H%M%S)
echo "== 1 donor_hybrid.cmd -t 16 -> 8 (применится при следующем старте донора автотренингом; сейчас без перезапуска)"
F=$N/agent/autotrain/donor_hybrid.cmd; cp -p $F $F.bak_p3_$D
python3 - "$F" <<'PY'
import sys
f=sys.argv[1]; L=open(f).read().split("\n")
for i,x in enumerate(L):
    if x=="-t" and i+1<len(L) and L[i+1]=="16": L[i+1]="8"; print("patched -t 8 at line",i+2)
open(f,"w").write("\n".join(L))
PY
grep -n -A1 -x -- "-t" $F | head -3
echo "== 2 swappiness"; cat /proc/sys/vm/swappiness; sysctl -w vm.swappiness=100 2>&1 | head -2; cat /proc/sys/vm/swappiness; sysctl -w vm.vfs_cache_pressure=50 2>&1 | head -1
echo "== 3 baseline slots sampling 20s"; for i in 1 2 3 4; do curl -s -m3 127.0.0.1:8104/slots | python3 -c "import sys,json;print('busy',sum(1 for s in json.load(sys.stdin) if s['is_processing']))"; sleep 5; done
cat > /tmp/p3_chain.sh <<'EOC'
#!/bin/bash
S=/workspace/nox/state/p3; O=$S/chain_$1.txt
cat > /tmp/p3_t.py <<'PY'
import json,time,http.client
for q in ("Привет! Как дела?","Расскажи в пяти предложениях о Севастополе."):
    t=time.time()
    try:
        c=http.client.HTTPConnection("127.0.0.1",8104,timeout=60)
        c.request("POST","/v1/chat/completions",json.dumps({"messages":[{"role":"user","content":q}],"max_tokens":100,"stream":True,"chat_template_kwargs":{"enable_thinking":False}}),{"Content-Type":"application/json"})
        r=c.getresponse();ft=None;n=0
        while True:
            l=r.readline()
            if not l:break
            if l.startswith(b"data:") and b'"content":"' in l and b'"content":""' not in l:
                n+=1
                if ft is None: ft=time.time()-t
        tt=time.time()-t
        print("ttft_s",ft and round(ft,2),"total_s",round(tt,1),"tok_s",ft and n>1 and round((n-1)/(tt-ft),1))
    except Exception as e: print("ERR",type(e).__name__,round(time.time()-t,1))
PY
{ echo "== BEFORE-EXCL $(date +%T) load $(cut -d' ' -f1-3 /proc/loadavg)"; timeout 130 python3 /tmp/p3_t.py
  echo "== apply exclusive pin"; /workspace/nox/ops/p3_excl_once.sh; sleep 20
  echo "== AFTER-EXCL $(date +%T) load $(cut -d' ' -f1-3 /proc/loadavg)"; timeout 130 python3 /tmp/p3_t.py
  echo "== procs on chat cores (8-15,24-31) sampled"; top -H -b -d 5 -n 2 -w 150 | awk '/^top -/{n++} n>=2' | awk '($9+0)>=15' | head -14
  echo DONE; } > $O 2>&1
EOC
chmod +x /tmp/p3_chain.sh
echo "== 4 exclusive pin script"
cat > $N/ops/p3_excl_once.sh <<'EOX'
#!/bin/bash
# P3: все процессы кроме чата уходят с ядер чата. Откат: taskset -a -cp 0-31 для pid из state/p3/cpu_backup_*.txt
CHATSET="8-15,24-31"; OTHER="0-7,16-23"
chat_re='llama-server.*--port 8104|web_server.py|nox_core.py|llama-swap|nox_agents|p3_|sshd|supervisord|cloudflared|caddy'
for d in /proc/[0-9]*; do p=${d#/proc/}; [ "$p" -le 2 ] && continue; a=$(tr '\0' ' ' <$d/cmdline 2>/dev/null) || continue; [ -z "$a" ] && continue
  echo "$a" | grep -qE "$chat_re" && continue
  cur=$(taskset -cp $p 2>/dev/null | sed 's/.*: //'); case "$cur" in 0-31|*8-15*|*24-31*) taskset -a -cp $OTHER $p >/dev/null 2>&1;; esac
done
EOX
chmod +x $N/ops/p3_excl_once.sh
python3 - <<'PY'
p="/workspace/nox/ops/p3_cpuset_guard.sh"; s=open(p).read()
if "p3_excl_once" not in s:
    s=s.replace("  sleep 60","  /workspace/nox/ops/p3_excl_once.sh\n  sleep 60"); open(p,"w").write(s); print("guard patched")
PY
echo "== 5 restart guard"; kill $(cat $S/guard.pid) 2>/dev/null; nohup setsid $N/ops/p3_cpuset_guard.sh >/dev/null 2>&1 & echo $! > $S/guard.pid
nohup setsid /tmp/p3_chain.sh tune1 >/dev/null 2>&1 &
echo started chain
