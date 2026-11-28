echo "K1: o6_rec3"; export RUNNER_TRACKING_ID=""
N=/workspace/nox
python3 -I - <<'PY'
import json,os,glob,time
N="/workspace/nox"
def shp(v,d=0):
    if isinstance(v,dict): return {k:(shp(x,d+1) if d<1 else type(x).__name__) for k,x in list(v.items())[:25]}
    if isinstance(v,list): return "list[%d]"%len(v)
    if isinstance(v,(int,float)): return round(v,3)
    if isinstance(v,str): return "str(%d)"%len(v) if len(v)>30 else v
    return v
for p in glob.glob(N+"/state/genesis_ledger.json")+glob.glob(N+"/state/core/genesis_ledger.json"):
    print("GL",p,os.path.getsize(p),round((time.time()-os.path.getmtime(p))/3600,1),"h")
    try: print(json.dumps(shp(json.load(open(p,encoding="utf-8"))),ensure_ascii=False)[:900])
    except Exception as e: print("ERR",e)
p=N+"/state/core/genesis_chain.jsonl"
if os.path.exists(p):
    L=open(p,encoding="utf-8").read().splitlines(); print("GC lines",len(L),round((time.time()-os.path.getmtime(p))/3600,1),"h")
    for l in L[:2]+L[-1:]:
        try: print(" ",json.dumps(shp(json.loads(l)),ensure_ascii=False)[:500])
        except Exception: print("  notjson")
print("find genesis:",[x for x in glob.glob(N+"/**/*genesis*",recursive=True) if "/archive/" not in x and "node_modules" not in x and "venv" not in x and "/p3/eval" not in x][:15])
PY
echo "== writers"; grep -lE "dream\.jsonl" $N/mods/*.py $N/agent/nox_agents/*.py $N/brain/*/*.py $N/*.py 2>/dev/null | head -5
grep -rlE "genesis_chain|genesis_ledger" $N/mods $N/agent $N/brain $N/web/pkg 2>/dev/null --include=*.py | head -8
echo "== phase origin"; grep -rhoE "first_run[a-z_]*|born_first[a-z_]*|started_at[a-z_]*|first_launch[a-z_]*" $N/state/mind/*.json 2>/dev/null | sort | uniq -c | head; ls $N/state/mind | tr '\n' ' '; echo
grep -n "days_alive" -r $N/mods $N/agent/nox_agents $N/brain --include=*.py 2>/dev/null | head -4
echo "== gate/training logs"; find $N/state $N/agent -maxdepth 4 \( -iname '*gate*log*' -o -iname 'gate*.jsonl' -o -iname '*accepted*' -o -iname 'axis_rollback*' -o -iname '*train_progress*' -o -iname 'step_log*' \) -not -path '*/eval/*' 2>/dev/null | head -12 | while read f; do echo "$f $(stat -c '%s %Y' $f)"; done
echo "== trainer state"; ls -t $N/state/p3 2>/dev/null | head -15 | tr '\n' ' '; echo
echo "== journal feel ids (sid only)"; grep -o '"sid": *"[^"]*"' $N/state/core/journal.jsonl | sort | uniq -c | head -12
echo "== owner_active / silence"; ls $N/state/core | grep -iE "owner|silence|active" ; ls $N/state/core/chat_activity | head -3; cat $N/state/core/owner_active.json 2>/dev/null | head -c 400
echo "== quiet.py"; sed -n 1,25p $N/brain/COMMON/quiet.py
echo "== inspector sd"; sed -n 1,12p $N/mods/inspector.py | cut -c1-220
echo "== nox_dream? supervisor/cron"; crontab -l 2>/dev/null | grep -iE 'sleep|dream' | cut -c1-200; ps aux | grep -iE 'dream|mind' | grep -v grep | awk '{print $11,$12,$13}' | head -5
echo END
