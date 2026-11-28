# AUD2: read-only; numbers/names/bools only
N=/workspace/nox; S=$N/state/core; M=$N/state/mind; NOW=$(date +%s)
echo "AUD2 $(date +%F_%H:%M)"
EX="--exclude-dir=venv --exclude-dir=venv_tools --exclude-dir=build --exclude-dir=runtime --exclude-dir=vendor --exclude-dir=archive --exclude-dir=node_modules --exclude-dir=site-packages --exclude-dir=tmp --exclude-dir=.git --exclude-dir=th_ens_bak_* --exclude-dir=state --exclude-dir=models"
for k in "self_now" "dream.jsonl" "morning_brief_v5" "evening_brief_v5" "affect_owner_feed" "initiative.json" "calibration.json" "control_vectors" "logprobs" "workspace.json" "own_life" "life_loop" "nox_agents.sleep|import sleep|sleep.run" "birthday"; do echo "refs[$k]=$(grep -rlsE $EX --include=*.py "$k" $N 2>/dev/null | sed "s#$N/##" | head -8 | tr '\n' ',')"; done
echo "## cron (sched + script basenames only)"; crontab -l 2>/dev/null | grep -v '^#' | grep -i -E "sleep|morning|evening|dream|initiat|brief|exam|passport|birth|calib|ritual|life" | awk '{printf "%s %s %s %s %s ", $1,$2,$3,$4,$5; for(i=6;i<=NF;i++) if($i ~ /\.(py|sh)$/){n=split($i,a,"/"); printf "%s ", a[n]} print ""}'
python3 -I - <<'PY'
import json,os,time,glob,collections
N="/workspace/nox"; S=N+"/state/core"; M=N+"/state/mind"; NOW=time.time()
def L(p):
    try: return json.load(open(p,encoding="utf-8"))
    except Exception: return None
def sc(v):
    if isinstance(v,bool): return v
    if isinstance(v,(int,float)): return round(v,3)
    if v is None: return None
    if isinstance(v,str): return "str[%d]"%len(v)
    if isinstance(v,list): return "list[%d]"%len(v)
    if isinstance(v,dict): return "dict[%d]"%len(v)
def flat(d,pre="",depth=0):
    o={}
    if isinstance(d,dict):
        for k,v in d.items():
            if isinstance(v,dict) and depth<1: o.update(flat(v,pre+k+".",depth+1))
            else: o[pre+k]=sc(v)
    return o
def age(p): return round((NOW-os.path.getmtime(p))/3600,1) if os.path.exists(p) else None
print("## state/mind small jsons (key: scalar/len)")
for n in ["aliveness","initiative","life_loop","phase","control_vectors","council","rituals","own_life","strange_loop","salience","sdt","workspace","stance","veto","promises","evening_brief_v5","morning_brief_v5","dreamer","lessons","predictive","situation","context","immunity","traits","provenance","skills"]:
    d=L(M+"/%s.json"%n); print(n,"age_h=",age(M+"/%s.json"%n),flat(d) if isinstance(d,dict) else sc(d))
print("## agents control vectors"); d=L(N+"/state/agents/mind_control_vectors.json"); print(flat(d) if isinstance(d,dict) else sc(d))
sn=L(S+"/self_now.json")
print("## self_now", "age_h=",age(S+"/self_now.json"))
if isinstance(sn,dict):
    print({k:sc(v) for k,v in sn.items()})
    print("telemetry",flat(sn.get("telemetry")) if isinstance(sn.get("telemetry"),dict) else sc(sn.get("telemetry")))
    f=sn.get("feelings"); print("feelings n=",len(f) if hasattr(f,"__len__") else sc(f))
    if isinstance(f,list) and f and isinstance(f[0],dict): print("feeling keys",list(f[0].keys()))
print("## dream.jsonl")
p=M+"/dream.jsonl"; rows=[]
for l in open(p,encoding="utf-8",errors="ignore"):
    try: rows.append(json.loads(l))
    except Exception: pass
print("lines",len(rows)); 
if rows:
    print("last keys",{k:sc(v) for k,v in rows[-1].items()})
    def T(r):
        t=r.get("ts") or r.get("time") or r.get("t")
        try: return float(t) if not isinstance(t,str) else time.mktime(time.strptime(t[:19].replace("T"," "),"%Y-%m-%d %H:%M:%S"))
        except Exception: return 0
    ts=[T(r) for r in rows if T(r)]
    if ts:
        print("first_age_h=%.0f last_age_h=%.1f"%((NOW-min(ts))/3600,(NOW-max(ts))/3600))
        days=collections.Counter(time.strftime("%m-%d",time.localtime(t)) for t in ts); print("per_day",dict(sorted(days.items())[-6:]))
        hrs=collections.Counter(time.strftime("%H",time.localtime(t)) for t in ts if t>NOW-172800); print("hours_48h",dict(sorted(hrs.items())))
    for key in ("phase","kind","type","stage","mode"):
        c=collections.Counter(str(r.get(key)) for r in rows if key in r)
        if c: print("by",key,dict(c.most_common(10)))
print("## affect_owner_feed")
p=S+"/affect_owner_feed.jsonl"; rows=[]
for l in open(p,encoding="utf-8",errors="ignore"):
    try: rows.append(json.loads(l))
    except Exception: pass
print("lines",len(rows),"age_h",age(p))
if rows: print("last keys/numerics",{k:sc(v) for k,v in rows[-1].items() if not isinstance(v,str) or k in("kind","type","label","emotion")})
print("## stages canon"); d=L(N+"/canon/stages.json"); print(flat(d) if isinstance(d,dict) else sc(d))
pp=L(S+"/passport.json"); print("passport stage",pp.get("stage"),"stage_name_len",len(str(pp.get("stage_name",""))),"source_len",len(str(pp.get("source",""))),"self_report.source_len",len(str((pp.get("self_report") or {}).get("source",""))),"self_report.model_len",len(str((pp.get("self_report") or {}).get("model",""))), "self_report.age_h", round((NOW-float((pp.get("self_report") or {}).get("ts",0)))/3600,1) if isinstance((pp.get("self_report") or {}).get("ts"),(int,float)) else "na")
sr=(pp.get("self_report") or {}).get("fields"); print("self_report.fields type",type(sr).__name__, (list(sr.keys()) if isinstance(sr,dict) else sr if isinstance(sr,list) and all(len(str(x))<30 for x in sr) else "len%d"%len(sr)))
print("owner-filled keys: addressing/voice_anchor/hexaco_status ->", sc(pp.get("hexaco_status")), sc(pp.get("voice_anchor")))
print("## predictions/immunity lines")
for f in ("predictions.jsonl","immunity.jsonl","traits.jsonl"):
    p=M+"/"+f; print(f,"lines",sum(1 for _ in open(p,encoding="utf-8",errors="ignore")),"age_h",age(p))
p=N+"/state/s03_recall.log"; print("s03_recall.log age_h",age(p)); 
if os.path.exists(p):
    hs=collections.Counter(l[:2] for l in open(p,errors="ignore").readlines()[-300:]); print("hour hist last300",dict(sorted(hs.items())))
PY
echo "## sleep.py defs / last run evidence"; grep -c "^def " $N/agent/nox_agents/sleep.py; grep -o "^def [a-z_]*" $N/agent/nox_agents/sleep.py | tr '\n' ' '; echo
ls -la --time-style=+%m-%d_%H:%M $N/agent/nox_agents 2>/dev/null | awk '{print $6, $7}' | head -40
echo "agents state files modified last 24h: $(find $N/state/agents -type f -mmin -1440 2>/dev/null | wc -l)"
find $N/state/agents -maxdepth 1 -type f \( -iname "*sleep*" -o -iname "*dream*" -o -iname "*morning*" -o -iname "*evening*" -o -iname "*nrem*" -o -iname "*rem*" \) -printf '%f %s %TY-%Tm-%Td_%TH:%TM\n' 2>/dev/null | head -15
echo END
