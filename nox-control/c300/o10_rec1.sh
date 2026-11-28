echo "K1: o10_rec1"; export RUNNER_TRACKING_ID=""
N=/workspace/nox
python3 -I - <<'PY'
import json,os,re,glob,collections,time,urllib.request
N="/workspace/nox"
c=collections.Counter(); ex={}
for l in open(N+"/state/chat_gate.log",encoding="utf-8",errors="ignore").read().splitlines():
    m=re.match(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\s+(\S+)(.*)",l)
    if m:
        k=m.group(1); c[k]+=1
        if k not in ex: ex[k]=re.sub(r"[А-Яа-яЁё]+","W",re.sub(r"\d+","9",m.group(2)))[:90]
print("GATE tags",dict(c.most_common(25)))
for k,v in list(ex.items())[:14]: print("  ex",k,"|",v)
print("gate files",[os.path.relpath(p,N) for p in glob.glob(N+"/state/*gate*")+glob.glob(N+"/state/core/*gate*")+glob.glob(N+"/state/mind/*gate*")][:12])
def sh(v):
    if isinstance(v,dict): return {k:(type(x).__name__ if isinstance(x,(dict,list)) else (round(x,2) if isinstance(x,float) else (x if isinstance(x,(int,bool)) or (isinstance(x,str) and len(x)<16) else "str"))) for k,x in list(v.items())[:14]}
    return type(v).__name__
S=N+"/state/core"
for f in ("hunger.json","hunt_requests.json","unknown_map.json","worm_goals.json"):
    try:
        d=json.load(open(S+"/"+f,encoding="utf-8")); print(f,json.dumps(sh(d),ensure_ascii=False)[:400])
        if isinstance(d,dict) and isinstance(d.get("requests"),list): print("  n_requests",len(d["requests"]),[ (r.get("status"),r.get("license")) for r in d["requests"][:6]])
        if isinstance(d,dict) and isinstance(d.get("topics"),dict): print("  n_topics",len(d["topics"]))
    except Exception as e: print(f,"ERR",type(e).__name__)
mb=json.load(open(N+"/state/mind/morning_brief_v5.json",encoding="utf-8")); print("morning keys",list(mb.keys()),"nlines",len(mb.get("lines",[])),"age_h",round((time.time()-os.path.getmtime(N+"/state/mind/morning_brief_v5.json"))/3600,1))
print("worm files",[os.path.relpath(p,N) for p in glob.glob(N+"/**/*worm*",recursive=True) if "/archive/" not in p and "site-packages" not in p and "node_modules" not in p][:14])
print("catalogs",[ (os.path.relpath(p,N),os.path.getsize(p)) for p in glob.glob(N+"/**/*catalog*.json*",recursive=True) if "site-packages" not in p and "node_modules" not in p][:8])
print("stop files",[os.path.exists(p) for p in (N+"/STOP","/run/nox/STOP",N+"/state/agents.off")])
for u in ("https://huggingface.co/api/datasets?search=russian%20dialogue&limit=2","https://api.github.com/search/repositories?q=russian+dialogue+dataset&per_page=2"):
    try:
        r=urllib.request.urlopen(urllib.request.Request(u,headers={"User-Agent":"nox-scanner-meta"}),timeout=15); b=r.read(); d=json.loads(b)
        print("NET",u.split("/")[2],r.status,len(b),"keys",list((d[0] if isinstance(d,list) else d.get("items",[{}])[0]).keys())[:14], "ratelimit",r.headers.get("x-ratelimit-remaining"))
    except Exception as e: print("NET",u.split("/")[2],"ERR",type(e).__name__,str(e)[:60])
PY
echo END
