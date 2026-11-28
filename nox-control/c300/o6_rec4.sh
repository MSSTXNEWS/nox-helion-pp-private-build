echo "K1: o6_rec4"; export RUNNER_TRACKING_ID=""
N=/workspace/nox
python3 -I - <<'PY'
import json,os,glob,time,re,collections
N="/workspace/nox"
def shp(v,d=0):
    if isinstance(v,dict): return {k:(shp(x,d+1) if d<1 else type(x).__name__) for k,x in list(v.items())[:25]}
    if isinstance(v,list): return "list[%d]"%len(v)
    if isinstance(v,(int,float)): return round(v,3)
    if isinstance(v,str): return "str(%d)"%len(v) if len(v)>24 else v
    return v
def tail(p,n=3):
    L=open(p,encoding="utf-8",errors="ignore").read().splitlines(); print("FILE",p,"lines",len(L),"age_min",round((time.time()-os.path.getmtime(p))/60))
    for l in L[-n:]:
        try: print("   J",json.dumps(shp(json.loads(l)),ensure_ascii=False)[:420])
        except Exception: print("   T",re.sub(r"\d","9"," ".join(l.split()[:4]))[:80])
for p in (N+"/state/chat_gate.log",N+"/state/LISKA_GATES_LOG.jsonl",N+"/state/p3/axis_rollback.jsonl"): tail(p)
for p in (N+"/state/p3/train_verdict.json",N+"/state/p3/guard_eval.json",N+"/state/p3/inspector_heartbeat.json"):
    try: print("JSON",p,json.dumps(shp(json.load(open(p,encoding="utf-8"))),ensure_ascii=False)[:600])
    except Exception as e: print(p,"ERR",e)
# tasks
c=collections.Counter(); newest=0
for p in glob.glob(N+"/state/tasks/*.json")[:3000]:
    try: d=json.load(open(p,encoding="utf-8")); c[str(d.get("status"))]+=1; newest=max(newest,os.path.getmtime(p))
    except Exception: c["bad"]+=1
print("TASKS status",dict(c),"newest_age_min",round((time.time()-newest)/60) if newest else None)
ex=glob.glob(N+"/state/tasks/*.json")[:1]
if ex:
    d=json.load(open(ex[0],encoding="utf-8")); print("TASK keys",json.dumps(shp(d),ensure_ascii=False)[:400])
# training progress logs
fs=[]
for pat in (N+"/agent/autotrain/*",N+"/state/p3/*.log",N+"/logs/*train*",N+"/logs/*dpo*",N+"/ops/dpo/*.log"):
    for p in glob.glob(pat):
        if os.path.isfile(p): fs.append((os.path.getmtime(p),p))
fs.sort(reverse=True)
for m,p in fs[:10]: print("TRAINF",p,os.path.getsize(p),round((time.time()-m)/60),"min")
for m,p in fs[:10]:
    if p.endswith((".log",".jsonl",".txt")):
        L=open(p,encoding="utf-8",errors="ignore").read().splitlines()[-2:]
        for l in L: print("  TT",re.sub(r"[A-Za-zА-Яа-я_]{12,}","W",l)[:200])
        break
# accepted adapters / ledger
print("ACCEPTED", glob.glob(N+"/agent/autotrain/accepted*")[:3], len(glob.glob(N+"/state/p3/**/accepted*",recursive=True)))
p=N+"/state/core/episodes.jsonl"; c=collections.Counter(); k=collections.Counter()
for l in open(p,encoding="utf-8",errors="ignore"):
    try: d=json.loads(l); c[d.get("src")]+=1; k[d.get("kind")]+=1
    except Exception: pass
print("EP src",dict(c.most_common(12))); print("EP kind",dict(k.most_common(12)))
d=json.loads(open(p,encoding="utf-8").read().splitlines()[-1]); print("EP last content keys",list((d.get("content") or {}).keys())[:15], "id",d.get("id"), "provenance",d.get("provenance"))
PY
echo "== train procs"; ps aux | grep -E 'train|dpo' | grep -v grep | awk '{print $11,$12,$13,$14}' | head -5
echo "== gpu"; nvidia-smi --query-gpu=power.draw,memory.used,memory.total,temperature.gpu,utilization.gpu --format=csv,noheader
echo "== STREAMS_NOTES on K1? none"; ls /home/claude/brain 2>&1 | head -2
echo END
