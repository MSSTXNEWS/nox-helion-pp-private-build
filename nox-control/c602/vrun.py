import json,urllib.request,time,re,sys,os,glob
OUT="/root/nox/state/c602_verify.json"
GW="http://127.0.0.1:8082/v1/chat/completions"
cid="c602-%d"%time.time()
Q=sys.argv[1:] or []
def chat(hist):
    b={"model":"nox","messages":hist,"stream":True,"nox_mode":"auto"}
    rq=urllib.request.Request(GW,json.dumps(b).encode(),{"Content-Type":"application/json","X-NOX-Conversation":cid,"X-NOX-Speaker":"owner"})
    txt="";nox=None;t=time.time();first=None
    with urllib.request.urlopen(rq,timeout=900) as r:
        for ln in r:
            ln=ln.decode("utf-8","replace").strip()
            if not ln.startswith("data:"): continue
            d=ln[5:].strip()
            if d=="[DONE]": break
            try: j=json.loads(d)
            except Exception: continue
            if j.get("nox"): nox=j["nox"]
            c=((j.get("choices") or [{}])[0].get("delta") or {}).get("content")
            if c:
                first=first or time.time()-t; txt+=c
    return txt.strip(),nox,round(time.time()-t,1),round(first or 0,1)
QS=["привет","как тебя ускорить?","объясни, что такое RAID 1","это грубо","расскажи о вселенной","это не ты придумал","увеличь длину ответа","убери ограничение длины","верни длину по умолчанию",
    "в чём разница между TCP и UDP?","почему небо голубое?","что такое индекс в базе данных?","как работает кэш процессора?","зачем нужен swap?"]
res=[];hist=[]
for q in QS:
    hist.append({"role":"user","content":q})
    try: a,nox,dt,ft=chat(hist)
    except Exception as e: a,nox,dt,ft="",{"err":str(e)},0,0
    hist.append({"role":"assistant","content":a})
    sents=len(re.findall(r"[.!?…]",a))
    res.append({"q":q,"a":a,"len":len(a),"sent":sents,"tier":(nox or {}).get("tier"),"nox":nox,"s":dt,"ttft":ft,"intro":bool(re.match(r"\W*(Слышу|Принял|Понял|Готов к)",a)),"ty":bool(re.search(r"\b(ты|тебе|тебя|твой|твоя)\b",a,re.I)),"empty":not a})
    json.dump(res,open(OUT,"w"),ensure_ascii=False,indent=1)
open(OUT+".done","w").write("1")
