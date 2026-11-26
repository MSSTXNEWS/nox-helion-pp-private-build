#!/bin/bash
cat > /workspace/nox/state/p3/hang.py <<'PY'
import http.client,json,time
M=["Привет!","Сколько будет 12*12?","Что такое DNS?","Назови столицу Японии.","Как дела?","Дай совет по сну в двух предложениях."]
for i,m in enumerate(M):
    t0=time.time(); ev=[]; ft=None
    try:
        c=http.client.HTTPConnection("127.0.0.1",8091,timeout=100)
        c.request("POST","/api/turn",json.dumps({"conversation_id":"qa-hang-%d-%d"%(int(t0),i),"message":m}),{"Content-Type":"application/json"})
        r=c.getresponse(); buf=b""
        while time.time()-t0<95:
            ch=r.read1(4096)
            if not ch: break
            buf+=ch
            while b"\n" in buf:
                l,buf=buf.split(b"\n",1)
                try: f=json.loads(l)
                except Exception: continue
                k=f.get("t")
                if k=="delta" and ft is None and f.get("text","").strip(): ft=round(time.time()-t0,1)
                if k!="delta": ev.append((round(time.time()-t0,1),k,str(f.get("text") or f.get("status") or f.get("code") or "")[:60]))
    except Exception as e: ev.append(("ERR",repr(e)[:80]))
    print(i,"ttft",ft,"total",round(time.time()-t0,1),ev,flush=True)
PY
setsid -f /workspace/nox/venv/bin/python -I /workspace/nox/state/p3/hang.py > /workspace/nox/state/p3/hang.out 2>&1 < /dev/null
echo started
