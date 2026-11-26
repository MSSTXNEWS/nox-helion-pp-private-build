echo "C300: srv_k140"
cd /workspace/nox; date -u +%T; uptime | sed 's/.*load/load/'; tail -n 3 agent/out/chat_priority.log | cut -c1-160
cat > /tmp/k1probe.py <<'PY'
import json,time,sys,http.client
port=int(sys.argv[1]); cid="qa-k1probe-%d"%int(time.time())
for q in ("Привет, NOX! Как дела?","Расскажи в двух предложениях, что такое чёрная дыра."):
    t0=time.time(); c=http.client.HTTPConnection("127.0.0.1",port,timeout=120)
    c.request("POST","/api/turn",body=json.dumps({"conversation_id":cid,"message":q},ensure_ascii=False).encode(),headers={"Content-Type":"application/json"})
    r=c.getresponse(); print(port,"заголовки %.2f"%(time.time()-t0),r.status,flush=True); n=0; ev=[]
    while True:
        l=r.readline()
        if not l: break
        try: o=json.loads(l)
        except Exception: continue
        n+=1; tp=o.get("t")
        if tp in("delta",) and not any(e[0]=="delta" for e in ev): ev.append(("delta",round(time.time()-t0,2)))
        elif tp!="delta": ev.append((tp,round(time.time()-t0,2)))
        if tp=="done": break
    print(port,q[:25],"события:",ev[:10],"итого %.2f"%(time.time()-t0),flush=True)
PY
for p in 8091 18091; do timeout 140 python3 /tmp/k1probe.py $p; done
tail -n 6 agent/out/chat_priority.log | cut -c1-160
