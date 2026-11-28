echo "K1: o6_rec2"; export RUNNER_TRACKING_ID=""
N=/workspace/nox
echo "== sleep.py"; cat $N/agent/nox_agents/sleep.py
echo "== who calls sleep"; grep -rlE "sleep\.tick|import sleep|sleep import|nox_agents.sleep" $N/agent $N/mods 2>/dev/null | head -5
echo "== episode.py defs"; grep -nE "^def |^class |^[A-Z_]+ *=" $N/agent/nox_agents/episode.py | head -30
echo "== lib consts"; grep -nE "^[A-Z_]+ *=" $N/agent/nox_agents/lib.py | head -20
echo "== gate_log"; find $N -name 'gate_log*' -not -path '*/archive/*' 2>/dev/null | head -5
echo "== inspector writes self_now?"; grep -ln "self_now" $N/mods/*.py $N/agent/nox_agents/*.py 2>/dev/null | head
python3 -I - <<'PY'
import json,os,time,glob
N="/workspace/nox"
def shp(v):
    if isinstance(v,dict): return {k:shp(x) if not isinstance(x,(dict,list)) else type(x).__name__ for k,x in list(v.items())[:30]}
    if isinstance(v,(int,float)): return round(v,3)
    if isinstance(v,str): return "str(%d)"%len(v)
    return v
for p in (N+"/state/mind/salience.json",N+"/state/mind/sdt.json",N+"/state/mind/lessons.json"):
    try:
        d=json.load(open(p,encoding="utf-8")); print("JSON",p,json.dumps(shp(d) if isinstance(d,dict) else "list[%d]"%len(d),ensure_ascii=False)[:1200])
        if isinstance(d,dict):
            for k,v in d.items():
                if isinstance(v,dict): print("   sub",k,json.dumps(shp(v),ensure_ascii=False)[:500])
    except Exception as e: print(p,"ERR",e)
for p in (N+"/state/core/episodes.jsonl",N+"/state/core/journal.jsonl",N+"/state/mind/dream.jsonl"):
    L=open(p,encoding="utf-8",errors="ignore").read().splitlines(); print("JL",p,len(L))
    ks={}
    for l in L[-300:]:
        try: d=json.loads(l)
        except Exception: continue
        for k,v in d.items(): ks.setdefault(k,type(v).__name__)
    print("  keys",ks)
    try:
        d=json.loads(L[-1]); print("  last numeric",{k:round(v,3) for k,v in d.items() if isinstance(v,(int,float))})
    except Exception: pass
# journal feeling sample ids/numbers only
for l in open(N+"/state/core/journal.jsonl",encoding="utf-8",errors="ignore"):
    try: d=json.loads(l)
    except Exception: continue
    if d.get("kind")=="feeling": print("FEEL",{k:(v if isinstance(v,(int,float)) or k in("kind","id","sensor","sev","ts") else "str") for k,v in d.items()}); break
p=json.load(open(N+"/state/core/passport.json",encoding="utf-8"))
print("approval",json.dumps(p.get("approval"),ensure_ascii=False)[:300]); print("provenance keys",list((p.get("provenance") or {}).keys())[:12]); print("stage",p.get("stage"),p.get("stage_name"))
m=json.load(open(N+"/state/mind/phase.json",encoding="utf-8")); print("phase",{k:(v if k in("ts","msk","days_alive","phase","status","component","drift_multiplier") else "str") for k,v in m.items()})
print("passport md5",__import__("hashlib").md5(open(N+"/state/core/passport.json","rb").read()).hexdigest())
print("born files", [os.path.basename(x) for x in glob.glob(N+"/state/*birth*")+glob.glob(N+"/state/core/*birth*")+glob.glob(N+"/state/core/*ledger*")+glob.glob(N+"/state/core/*genesis*")])
PY
echo "== supervisor include"; grep -nE "include|files" /etc/supervisor/supervisord.conf | head; ls /etc/supervisor/conf.d | head -50 | tr '\n' ' '; echo
echo "== quiet utils"; ls $N/brain/COMMON 2>/dev/null | tr '\n' ' '
echo "== python"; python3 -V; python3 -c "import pytest" 2>&1 | tail -1
echo "== disk"; df -BG /workspace | tail -1
echo END
