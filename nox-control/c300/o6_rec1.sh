echo "K1: o6_rec1"; export RUNNER_TRACKING_ID=""
N=/workspace/nox
for n in sleep.py dream.jsonl phase.json salience.json sdt.json affect_owner_feed.jsonl gate_log.jsonl passport.json self_now.json journal.jsonl episodes.jsonl; do echo "FIND $n: $(find $N -name $n -not -path '*/archive/*' -not -path '*/node_modules/*' 2>/dev/null | head -4 | tr '\n' ' ')"; done
echo "FIND sensorium: $(find $N -iname '*sensorium*' -not -path '*/archive/*' 2>/dev/null | head -6 | tr '\n' ' ')"
echo "FIND salience/sdt/affect: $(find $N/state $N/mods -iname '*salience*' -o -iname '*sdt*' -o -iname '*affect*' -o -iname '*episod*' -o -iname '*lesson*' -o -iname '*concept*' 2>/dev/null | head -20 | tr '\n' ' ')"
echo "supervisor conf dir: $(ls -d /etc/supervisor* 2>/dev/null | tr '\n' ' ')"; supervisorctl status 2>/dev/null | awk '{print $1"="$2}' | tr '\n' ' '; echo
echo "nvidia: $(nvidia-smi --query-gpu=memory.used,memory.total,temperature.gpu,utilization.gpu --format=csv,noheader 2>&1|head -1)"
python3 -I - <<'PY'
import json,os,glob,time
N="/workspace/nox"
def shape(v,d=0):
    if isinstance(v,dict): return {k:shape(x,d+1) if d<2 else type(x).__name__ for k,x in list(v.items())[:25]}
    if isinstance(v,list): return "list[%d]"%len(v)
    if isinstance(v,(int,float)): return round(v,3)
    if isinstance(v,str): return "str(%d)"%len(v)
    return v
def show(p):
    try: d=json.load(open(p,encoding="utf-8")); print("JSON",p,json.dumps(shape(d),ensure_ascii=False)[:1500])
    except Exception as e: print("JSON",p,"ERR",type(e).__name__)
def jl(p,n=2):
    if not os.path.exists(p): print("JL",p,"absent"); return
    L=open(p,encoding="utf-8",errors="ignore").read().splitlines(); print("JL",p,"lines",len(L),"age_h",round((time.time()-os.path.getmtime(p))/3600,1))
    for l in L[-n:]:
        try: d=json.loads(l); print("  ",json.dumps(shape(d),ensure_ascii=False)[:600])
        except Exception: print("   notjson")
S=N+"/state/core"
for f in ("self_now.json","salience.json","sdt.json","phase.json","predictive.json","workspace.json","life_loop.json","hardware.json"):
    show(S+"/"+f)
for p in glob.glob(N+"/state/**/phase.json",recursive=True)[:3]: show(p)
try:
    pp=json.load(open(S+"/passport.json",encoding="utf-8")); t=pp.get("temperament",{}); print("TEMPERAMENT",json.dumps(t.get("drives_thresholds",t),ensure_ascii=False)[:1200]); print("PASSPORT top keys",list(pp.keys())[:40]); print("born_at",pp.get("born_at"),"approved",{k:(v if not isinstance(v,(dict,list)) else type(v).__name__) for k,v in pp.items() if "approv" in k.lower() or "provenance" in k.lower() or "утвер" in k.lower()})
except Exception as e: print("passport ERR",e)
for p in ("journal.jsonl","affect_owner_feed.jsonl","predictions.jsonl"): jl(S+"/"+p,2)
for p in glob.glob(N+"/state/**/gate_log.jsonl",recursive=True)[:2]: jl(p,2)
for p in glob.glob(N+"/state/**/dream.jsonl",recursive=True)[:2]+glob.glob(N+"/**/dream.jsonl",recursive=True)[:2]: jl(p,2)
import collections
c=collections.Counter()
try:
    for l in open(S+"/journal.jsonl",encoding="utf-8",errors="ignore"):
        try: c[json.loads(l).get("kind")]+=1
        except Exception: pass
except Exception: pass
print("JOURNAL kinds",dict(c.most_common(15)))
PY
echo "SLEEP.PY"; for f in $(find $N -name 'sleep*.py' -not -path '*/archive/*' 2>/dev/null | head -3); do echo "$f lines=$(wc -l <$f) md5=$(md5sum $f|cut -c1-8)"; grep -nE "^def |^import|^from|dream|cursor|supervisor|__main__|argv" $f | head -50; done
echo "who runs sleep: $(ps aux | grep -E 'sleep\.py|dream' | grep -v grep | awk '{print $11,$12,$13,$14}' | head -4)"
echo "cron: $(crontab -l 2>/dev/null | grep -ciE 'sleep|dream')"
echo "episodes: $(find $N/state -iname '*episod*' 2>/dev/null | head -3 | tr '\n' ' ')"; ls $N/state | head -60 | tr '\n' ' '; echo
ls $N/state/core | tr '\n' ' '; echo
df -h /workspace | tail -1
echo END
