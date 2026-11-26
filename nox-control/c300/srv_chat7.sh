#!/bin/bash
cat > /tmp/srv_t2.py <<'PY'
import http.client,json,time
for i,m in enumerate(["Привет! Как дела?","Что такое DNS? Два предложения."]):
    t0=time.time(); ev=[]
    c=http.client.HTTPConnection("127.0.0.1",8091,timeout=80)
    c.request("POST","/api/turn",json.dumps({"conversation_id":"qa-spd2-%d-%d"%(int(t0),i),"message":m}),{"Content-Type":"application/json"})
    r=c.getresponse(); buf=b""
    while True:
        ch=r.read1(4096)
        if not ch: break
        buf+=ch
        while b"\n" in buf:
            l,buf=buf.split(b"\n",1)
            try: f=json.loads(l)
            except Exception: continue
            k=f.get("t"); 
            if k=="delta": k+=":"+f.get("text","")[:25].replace("\n"," ")
            elif k in("level","meta"): k+=":"+json.dumps({a:b for a,b in f.items() if a!="t"},ensure_ascii=False)[:90]
            ev.append((round(time.time()-t0,1),k))
    print(i,"total",round(time.time()-t0,1)); 
    last=None
    for t,k in ev:
        if k.startswith("delta") and last and last.startswith("delta"): last=k; continue
        print("  ",t,k); last=k
PY
python3 /tmp/srv_t2.py
echo == train; tail -2 /workspace/nox/agent/autotrain/rounds/r031/train.log | cut -c1-200
echo == cpuset; for p in $(pgrep -f 'port 8104'|head -1) $(pgrep -f distill_v2|head -1); do echo $p $(grep Cpus_allowed_list /proc/$p/status) nice=$(ps -o ni= -p $p); done
