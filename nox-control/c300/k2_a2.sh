echo "C300: k2_a2"
N=/workspace/nox; A=$N/agent/autotrain; ST=$N/state
echo "--- t_coder disable"
cp -n $N/stewards/orch_registry.json $N/stewards/orch_registry.json.bak_k2
python3 - <<'P'
import json
f="/workspace/nox/stewards/orch_registry.json"; r=json.load(open(f))
js=r["jobs"] if isinstance(r,dict) and "jobs" in r else r
n=0
for j in (js if isinstance(js,list) else []):
    if j.get("name")=="t_coder": j["enabled"]=False; n+=1
json.dump(r,open(f,"w"),ensure_ascii=False,indent=1); print("t_coder disabled",n)
P
echo "--- cmd parallel 4"
for f in $A/donor_hybrid.cmd $A/donor_gpu.cmd; do cp -n $f $f.bak_k2
python3 - "$f" <<'P'
import sys
f=sys.argv[1]; L=open(f).read().split("\n")
for i,x in enumerate(L):
    if x=="--parallel" and i+1<len(L): print(f.split("/")[-1],"parallel",L[i+1],"->4"); L[i+1]="4"
open(f,"w").write("\n".join(L))
P
done
echo "--- emo_tick slot 0->3"
E=$N/brain/BRAIN/emo_tick.py; cp -n $E $E.bak_k2; sed -i 's/"id_slot": 0, "cache_prompt"/"id_slot": 3, "cache_prompt"/' $E; grep -c '"id_slot": 3' $E
echo "--- restart job"
cat > $ST/k2_restart_job.sh <<'J'
#!/bin/bash
N=/workspace/nox; L=$N/state/k2_restart.log
log(){ echo "$(date -u +%T) $*" >> $L; }
for i in $(seq 120); do
  age=$(( $(date +%s) - $(stat -c %Y $N/state/orch/OWNER_ACTIVE) ))
  if [ $age -gt 600 ]; then
    log "OWNER age ${age}s -> restart"
    bash $N/ops/body_restart.sh --reason "k2: parallel 4, slot0 chat-only" >> $L 2>&1; rc=$?
    log "body_restart rc=$rc"; [ $rc = 0 ] && break
  else [ $((i%4)) = 0 ] && log "wait owner age=${age}s"; fi
  sleep 30
done
sleep 5
V=$(nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits | awk -F, '{printf "%.1f",100*$1/$2}'); log "VRAM $V%"
awk -v v=$V 'BEGIN{exit !(v>92)}' && { log "VRAM>92 -> rollback known-good"; bash $N/ops/body_restart.sh --known-good --force --reason "k2 vram rollback" >> $L 2>&1; exit; }
log "slots: $(curl -s -m5 localhost:8104/slots | python3 -c 'import sys,json;print(len(json.load(sys.stdin)))' 2>&1)"
cat > /tmp/k2_turn.py <<'P'
import http.client,json,time,sys
def turn(m,tag):
    t0=time.time(); ft=None; last=None; txt=""
    for port in (18091,8091):
        try:
            c=http.client.HTTPConnection("127.0.0.1",port,timeout=60)
            c.request("POST","/api/turn",json.dumps({"conversation_id":"qa-k2-%s-%d"%(tag,int(t0)),"message":m}),{"Content-Type":"application/json"})
            r=c.getresponse()
            if r.status!=200: print(tag,port,"status",r.status); continue
            buf=b""
            while time.time()-t0<55:
                ch=r.read1(4096)
                if not ch: break
                buf+=ch
                while b"\n" in buf:
                    l,buf=buf.split(b"\n",1)
                    try: f=json.loads(l)
                    except Exception: continue
                    if f.get("t")=="delta" and f.get("text","").strip():
                        if ft is None: ft=time.time()-t0
                        txt+=f["text"]
                    if f.get("t")=="done": last=round(time.time()-t0,1)
            break
        except Exception as e: last="err "+str(e)[:50]
    print(tag,"port",port,"ttft",ft and round(ft,2),"done",last,"|",txt[:50].replace("\n"," "),flush=True)
turn(sys.argv[1],sys.argv[2])
P
log "warm: $(python3 /tmp/k2_turn.py 'Привет!' warm 2>&1 | tail -1)"
i=0; for m in "Как дела? Расскажи коротко." "Сколько будет 17*23?" "Что такое DNS?"; do i=$((i+1)); sleep 310; log "T$i: $(python3 /tmp/k2_turn.py "$m" t$i 2>&1 | tail -1)"; done
log "MEASURE DONE"
J
chmod +x $ST/k2_restart_job.sh; : > $ST/k2_restart.log
env RUNNER_TRACKING_ID=k2rs setsid -f bash $ST/k2_restart_job.sh </dev/null >/dev/null 2>&1
sleep 5; cat $ST/k2_restart.log; stat -c '%y' $ST/orch/OWNER_ACTIVE
ls -la $N/models/subcores/Qwen3-30B-A3B-Thinking-2507-GGUF/ | tail -1 | cut -c20-90; pgrep -f "Thinking-2507-Q4" | head -2
