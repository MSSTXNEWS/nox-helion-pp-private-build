echo "K1: ready1"
# Готовность ИИ: только числа и коды.
python3 - <<'PY'
import json,time,urllib.request,uuid,os
def code(u,data=None,to=8):
    t0=time.time()
    try:
        r=urllib.request.urlopen(urllib.request.Request(u,json.dumps(data).encode() if data else None,{"Content-Type":"application/json"}),timeout=to); return r.status,round(time.time()-t0,2)
    except urllib.error.HTTPError as e: return e.code,round(time.time()-t0,2)
    except Exception as e: return type(e).__name__,round(time.time()-t0,2)
for n,u in [("body8104","http://127.0.0.1:8104/health"),("gw8793","http://127.0.0.1:8793/health/liveliness"),("judge8300","http://127.0.0.1:8300/health"),("rte8084","http://127.0.0.1:8084/health"),("mem18220","http://127.0.0.1:18220/health"),("guard18218","http://127.0.0.1:18218/health"),("stt8093","http://127.0.0.1:8093/health"),("searx","http://127.0.0.1:8888/healthz"),("web8091","http://127.0.0.1:8091/api/health")]:
    print("SVC",n,*code(u))
print("JUDGE_FAST",*code("http://127.0.0.1:8300/judge",{"fast":True,"question":"2+2?","answer":"4"},30))
st="/workspace/nox/state"
for f in ("chat_fast.off","chat_v102.off","deep_adv.off","chat_slotpick.off","chat_idstance.off","s03_recall.off","owner_active"):
    print("FLAG",f,int(os.path.exists(os.path.join(st,f))))
U="http://127.0.0.1:18091/api/turn"
qs=["Привет","Сколько будет 17*23?","Объясни коротко, что такое DNS","Придумай название для кофейни","Что ты умеешь?","Как дела?","Переведи на английский: доброе утро","Назови три планеты"]
tt=[];tot=[];ok=0
for q in qs:
    cid="rv-"+uuid.uuid4().hex[:6];t0=time.time();first=None;done=0;L=0
    try:
        r=urllib.request.urlopen(urllib.request.Request(U,json.dumps({"conversation_id":cid,"message":q,"mode":"fast"}).encode(),{"Content-Type":"application/json"}),timeout=90)
        for ln in r:
            try:o=json.loads(ln.decode("utf8","replace"))
            except Exception:continue
            k=str(o.get("t") or o.get("type") or o.get("event"));d=o.get("delta") or o.get("text") or o.get("d")
            if d and k in("delta","d","text","token"):
                L+=len(d)
                if first is None:first=time.time()-t0
            if k in("done","error"):done=int(k=="done");break
    except Exception as e: print("TURN_EXC",type(e).__name__)
    s=time.time()-t0; ok+=done; tot.append(s)
    if first is not None: tt.append(first)
    print("TURN ttft=%s total=%.1f done=%d len=%d"%(None if first is None else round(first,2),s,done,L))
tt.sort();tot.sort()
med=lambda a:a[len(a)//2] if a else None
print("SUMMARY ok=%d/%d ttft_med=%s ttft_max=%s total_med=%s total_max=%s"%(ok,len(qs),med(tt) and round(med(tt),2),tt and round(max(tt),2),med(tot) and round(med(tot),1),tot and round(max(tot),1)))
print("LOAD",open("/proc/loadavg").read().split()[0])
PY
bash /dev/stdin <<<"$(curl -fsSL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/rv_turn.sh 2>/dev/null)" 2>&1 | grep -E "^(MEM|ADDR|JM|DRAW|IMG|HEALTH)"
echo END
