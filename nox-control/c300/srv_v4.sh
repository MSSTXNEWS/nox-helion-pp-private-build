#!/bin/bash
curl -s -m4 127.0.0.1:8300/health | head -c 700; echo
python3 -I - <<'PY'
import json,time,urllib.request
def j(t,c):
    rq=urllib.request.Request("http://127.0.0.1:8300/judge",data=json.dumps({"text":t,"context":c,"source":None,"role":"answer"}).encode(),headers={"Content-Type":"application/json","X-NOX-Priority":"chat"})
    s=time.time()
    try: r=json.load(urllib.request.urlopen(rq,timeout=60))
    except Exception as e: return round(time.time()-s,1),repr(e)[:60]
    return round(time.time()-s,1),{k:(v.get("status"),round(v.get("latency",0),1) if isinstance(v,dict) else 0) for k,v in (r.get("judges") or {}).items()}
for i in range(3): print(j("Токио — столица Японии. Это крупный город на острове Хонсю.","Назови столицу Японии."))
PY
ls /workspace/nox/judges | head -20; grep -n -E "device|cuda|num_threads|set_num_threads|max_length|ThreadPool|workers" /workspace/nox/judges/judge_service.py | head -20 | cut -c1-170
