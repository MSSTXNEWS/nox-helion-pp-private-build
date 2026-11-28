echo "K1: s6l_d5"
python3 -I - <<'PY'
import json,urllib.request,time,collections
for CH in ("http://127.0.0.1:18091","http://127.0.0.1:8091"):
  for msg in ("Объясни простыми словами: хэш-функция.","Привет!"):
    t0=time.time(); ev=collections.Counter(); n=0; txt=0; last=None
    try:
        resp=urllib.request.urlopen(urllib.request.Request(CH+"/api/turn",json.dumps({"conversation_id":"qa-pers-diag","message":msg,"mode":"fast","user_id":"qa_exam"}).encode(),{"Content-Type":"application/json"}),timeout=60)
        for ln in resp:
            if not ln.strip(): continue
            try: o=json.loads(ln)
            except Exception: ev["nonjson"]+=1; continue
            ev[str(o.get("t"))]+=1
            if o.get("t")=="delta": txt+=len(str(o.get("text") or o.get("delta") or ""))
            if o.get("t") in ("done","error","stopped"): last={k:(v if not isinstance(v,str) else len(v)) for k,v in o.items()}; break
    except Exception as e: last=type(e).__name__+" "+str(e)[:80]
    print(CH,len(msg),dict(ev),"chars",txt,"last",last,"sec",round(time.time()-t0,1))
PY
echo END
