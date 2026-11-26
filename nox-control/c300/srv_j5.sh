cat /workspace/nox/state/gpu_phase | head -c 80; echo
python3 -I - <<'PY'
import json,time,urllib.request
def j(t,c,fast=None):
    b={"text":t,"context":c,"source":None,"role":"answer"}
    if fast is not None: b["fast"]=fast
    rq=urllib.request.Request("http://127.0.0.1:8300/judge",data=json.dumps(b).encode(),headers={"Content-Type":"application/json","X-NOX-Priority":"chat"})
    s=time.time()
    try: r=json.load(urllib.request.urlopen(rq,timeout=90))
    except Exception as e: return round(time.time()-s,1),repr(e)[:60]
    return round(time.time()-s,1),len(r.get("judges") or {}),r.get("agg",{}).get("used"),r.get("flags")
for i in range(3): print("auto",j("Токио — столица Японии. Это крупный город на острове Хонсю.","Назови столицу Японии."))
print("fast",j("Токио — столица Японии.","Назови столицу Японии.",True))
PY
echo load $(cat /proc/loadavg)
