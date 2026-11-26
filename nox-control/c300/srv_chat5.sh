#!/bin/bash
cat > /tmp/srv_t.py <<'PY'
import http.client,json,time,sys
for i,m in enumerate(["Привет! Как дела?","Сколько будет 17*23?","Назови три столицы Европы.","Расскажи кратко, что такое TCP."]):
    t0=time.time(); ft=None; n=0; last=None
    try:
        c=http.client.HTTPConnection("127.0.0.1",8091,timeout=70)
        c.request("POST","/api/turn",json.dumps({"conversation_id":"qa-spd-%d-%d"%(int(t0),i),"message":m}),{"Content-Type":"application/json"})
        r=c.getresponse(); buf=b""
        while True:
            ch=r.read1(4096)
            if not ch: break
            buf+=ch
            while b"\n" in buf:
                l,buf=buf.split(b"\n",1)
                try: f=json.loads(l)
                except Exception: continue
                if f.get("t")=="delta" and f.get("text","").strip():
                    n+=len(f["text"])
                    if ft is None: ft=time.time()-t0
                last=f
    except Exception as e: last={"err":str(e)[:80]}
    print(i,"ttft",None if ft is None else round(ft,2),"total",round(time.time()-t0,1),"chars",n,"end",str(last)[:100])
PY
python3 /tmp/srv_t.py
curl -s -m3 127.0.0.1:8104/slots | python3 -c "import sys,json;print([s['is_processing'] for s in json.load(sys.stdin)])"
