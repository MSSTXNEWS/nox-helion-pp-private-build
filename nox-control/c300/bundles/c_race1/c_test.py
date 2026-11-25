import sys,json,urllib.request,time
msg,cid,tmo=sys.argv[1],sys.argv[2],int(sys.argv[3]); extra=json.loads(sys.argv[4]) if len(sys.argv)>4 else {}
b=dict({"conversation_id":cid,"message":msg},**extra)
rq=urllib.request.Request("http://127.0.0.1:8091/api/turn",data=json.dumps(b).encode(),headers={"Content-Type":"application/json"})
t=time.time(); ev={}; txt=""; race=None; m2=None
try:
    r=urllib.request.urlopen(rq,timeout=tmo)
    for l in r:
        l=l.decode("utf-8","replace").strip()
        if not l: continue
        try: o=json.loads(l)
        except Exception: continue
        k=o.get("t"); ev.setdefault(k,round(time.time()-t,1))
        if k=="delta": txt+=o.get("text","")
        if k=="race": race=o
        if k=="meta2" and not (o.get("meta") or {}).get("pending"): m2=o.get("meta")
        if k=="error": print("ERROREV",json.dumps(o,ensure_ascii=False)[:300])
    mm=m2 or {}
    print("Q:",msg[:50],"| first_delta_s=",ev.get("delta"),"| done_s=",ev.get("done"),"| race=",json.dumps(race,ensure_ascii=False) if race else None,"| conf=",mm.get("confidence"),"judges=",mm.get("judges"),"race_winner=",mm.get("race_winner"),"src=",mm.get("sources"))
    print("  ANSWER:",txt[:160].replace("\n"," "))
except Exception as e: print("ERR",msg[:40],str(e)[:200],ev)
