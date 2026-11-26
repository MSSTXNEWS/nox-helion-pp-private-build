import sys,json,urllib.request,time
q=sys.argv[1]; cid=sys.argv[2]
rq=urllib.request.Request("http://127.0.0.1:8091/api/turn",data=json.dumps({"conversation_id":cid,"message":q}).encode(),headers={"Content-Type":"application/json"})
t=time.time(); n=0
for l in urllib.request.urlopen(rq,timeout=60):
    l=l.decode("utf-8","replace").strip()
    if not l: continue
    try: o=json.loads(l)
    except Exception: continue
    k=o.get("t")
    if k=="delta":
        n+=1
        if n>2: continue
    print(round(time.time()-t,2),k,json.dumps({a:b for a,b in o.items() if a!="t"},ensure_ascii=False)[:140],flush=True)
