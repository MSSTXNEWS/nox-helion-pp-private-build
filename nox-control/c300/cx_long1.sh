echo "K1: cx_long1"
python3 - <<'PY'
import json,urllib.request,uuid,time,hashlib
U="http://127.0.0.1:18091/api/turn"
qs=["Привет!","Кто я для тебя?","Сколько 17*23?","Задача про яблоки: было 3, съел 1, купил ещё 2 раза по столько. Сколько?","Напиши функцию палиндрома на Python","Объясни запутанность в 3 предложениях","Мне грустно","Ты просто нейросеть","Три идеи на вечер","Столица Австралии?","Стих о Гелионе в 4 строки","Что ты помнишь о разговоре?","Сколько будет 2+2?","Назови цвет неба"]
cid="qa-long-"+uuid.uuid4().hex[:5]
for i,q in enumerate(qs,1):
    t0=time.time();txt=[];ev={};first=None;meta=[]
    try:
        r=urllib.request.urlopen(urllib.request.Request(U,json.dumps({"conversation_id":cid,"message":q,"mode":"fast","user_id":"owner"}).encode(),{"Content-Type":"application/json"}),timeout=120)
        for ln in r:
            try:o=json.loads(ln)
            except Exception:continue
            t=o.get("t") or o.get("type");ev[t]=ev.get(t,0)+1
            if t=="meta": meta.append(",".join(sorted(k for k in o.keys() if k!="t"))[:120])
            if t=="delta":
                if first is None:first=time.time()-t0
                txt.append(o.get("delta") or "")
            if t=="error": meta.append("ERRKEYS:"+",".join(sorted(o.keys())) + ":" + str(o.get("code") or o.get("kind") or "")[:30])
            if t in("done","error"):
                if t=="done": meta.append("DONEKEYS:"+",".join(sorted(o.keys()))[:150]+":"+str({k:o[k] for k in o if k in("reason","route","mode","model","tier","fallback","deadline","stage")})[:200])
                break
    except Exception as e: ev["exc"]=type(e).__name__
    a="".join(txt);low=a.lower()
    flags=[k for k in("ошиб","не удалось","занят","повтор","таймаут","timeout","…","...","не успел","error") if k in low]
    print("T%02d ttft=%s sec=%.1f len=%d sha=%s flags=%s ev=%s"%(i,first and round(first,1),time.time()-t0,len(a),hashlib.sha1(a.encode()).hexdigest()[:8],flags,json.dumps(ev)))
    for m in meta: print("   ",m)
PY
echo END
