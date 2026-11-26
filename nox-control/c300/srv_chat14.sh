#!/bin/bash
grep -n race_s /workspace/nox/state/persona.json
cat > /tmp/srv_t3.py <<'PY'
import http.client,json,time,sys
for i,m in enumerate(["Привет! Как дела?","Сколько будет 17*23?","Что такое DNS?"]):
    t0=time.time(); ft=None; last=None
    try:
        c=http.client.HTTPConnection("127.0.0.1",8091,timeout=45)
        c.request("POST","/api/turn",json.dumps({"conversation_id":"qa-spd3-%d-%d"%(int(t0),i),"message":m}),{"Content-Type":"application/json"})
        r=c.getresponse(); buf=b""
        while time.time()-t0<50:
            ch=r.read1(4096)
            if not ch: break
            buf+=ch
            while b"\n" in buf:
                l,buf=buf.split(b"\n",1)
                try: f=json.loads(l)
                except Exception: continue
                if f.get("t")=="delta" and f.get("text","").strip() and ft is None: ft=time.time()-t0
                if f.get("t")=="done": last=round(time.time()-t0,1)
    except Exception as e: last="err "+str(e)[:50]
    print(i,"ttft",ft and round(ft,2),"done",last,flush=True)
PY
timeout 200 python3 /tmp/srv_t3.py
