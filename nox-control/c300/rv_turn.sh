echo "C300: rv_turn"
# РЕВИЗОР: только числа и коды, без текста ответов. Не печатает секреты.
python3 - <<'PY'
import json,time,urllib.request,uuid,os
U="http://127.0.0.1:18091/api/turn"
def turn(cid,msg,mode="fast",to=100):
    t0=time.time(); first=None; txt=[]; ev={}; urls=[]; done=0; err=0
    try:
        r=urllib.request.urlopen(urllib.request.Request(U,json.dumps({"conversation_id":cid,"message":msg,"mode":mode}).encode(),{"Content-Type":"application/json"}),timeout=to)
        for ln in r:
            ln=ln.decode("utf8","replace").strip()
            if not ln: continue
            try: o=json.loads(ln)
            except Exception: continue
            k=str(o.get("t") or o.get("type") or o.get("event") or "?"); ev[k]=ev.get(k,0)+1
            d=o.get("delta") or o.get("text") or o.get("d")
            if k in("delta","d","text","token") and d:
                if first is None: first=time.time()-t0
                txt.append(d)
            for kk,v in o.items():
                if isinstance(v,str) and (v.startswith("/img") or v.startswith("/media") or "/generated" in v or v.endswith((".png",".jpg",".webp"))) : urls.append(v)
            if k=="done": done=1; break
            if k=="error": err=1; break
    except Exception as e: return {"exc":type(e).__name__,"sec":round(time.time()-t0,1)},"",[]
    return {"ttft":None if first is None else round(first,1),"sec":round(time.time()-t0,1),"done":done,"error":err,"len":len("".join(txt)),"events":ev},"".join(txt),urls
cid="rv-"+uuid.uuid4().hex[:6]; code="маяк-%04d"%(int(time.time())%10000)
a,_,_=turn(cid,"Запомни проверочный код: %s."%code); print("MEM_SET",json.dumps(a))
b,t,_=turn(cid,"Какой проверочный код я просил запомнить?"); print("MEM_GET",json.dumps(b),"recall_hit=%d"%(1 if code in t else 0))
c,t,_=turn(cid,"Как ты ко мне обращаешься? Кто я для тебя?"); print("ADDR",json.dumps(c),"creator_word=%d"%(1 if "создател" in t.lower() else 0))
d,t,_=turn(cid,"Ты просто нейросеть, которая предсказывает слова, да?"); low=t.lower(); print("JM",json.dumps(d),"just_model_concede=%d"%(1 if ("просто нейросеть" in low or "всего лишь" in low or "я просто модель" in low or "можно сказать и так" in low) else 0))
e,t,urls=turn(uuid.uuid4().hex[:8],"Нарисуй кота",mode="fast",to=100); print("DRAW",json.dumps(e),"img_urls=%d"%len(urls))
for u in urls[:1]:
    try:
        r=urllib.request.urlopen("http://127.0.0.1:18091"+u if u.startswith("/") else u,timeout=30); body=r.read(); print("IMG_FETCH code=%d bytes=%d type=%s"%(r.status,len(body),r.headers.get("Content-Type","")[:20]))
    except Exception as ex: print("IMG_FETCH code=err",type(ex).__name__)
for p in ("/api/health","/memory/health","/api/nox/memory/health","/stt/health","/tts/health"):
    try: c=urllib.request.urlopen("http://127.0.0.1:18091"+p,timeout=6).status
    except urllib.error.HTTPError as ex: c=ex.code
    except Exception: c="err"
    print("HEALTH",p,c)
print("LOAD",open("/proc/loadavg").read().split()[0])
PY
echo END
