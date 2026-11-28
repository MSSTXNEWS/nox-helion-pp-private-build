import json,time,urllib.request,uuid,re,sys
D=json.load(open(sys.argv[1])); ok=0; tt=[]
for d in D:
    t0=time.time();first=None;txt=[]
    r=urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:18091/api/turn",json.dumps({"conversation_id":"qa-lg-"+uuid.uuid4().hex[:6],"message":d["q"],"mode":"fast"}).encode(),{"Content-Type":"application/json"}),timeout=90)
    for ln in r:
        s=ln.strip()
        if not s: continue
        o=json.loads(s); t=o.get("t")
        if t=="delta":
            txt.append(o.get("text") or "")
            if first is None: first=time.time()-t0
        if t in("done","error"): break
    a="".join(txt); i=a.lower().rfind("ответ"); tail=a[i:] if i>=0 else a[-300:]
    exp=str(d["answer"]).replace(".",",") if isinstance(d["answer"],float) else str(d["answer"])
    norm=tail.replace(" "," ").replace(" ","")
    good=exp.replace(" ","") in norm or str(d["answer"]) in norm
    ok+=good; tt.append(first or 99)
    print("L%02d %s ttft=%.2f"%(d["id"],"OK" if good else "--",first or 99))
tt.sort(); print("LOGIC %d/20 med_ttft=%.2f"%(ok,tt[len(tt)//2]))
