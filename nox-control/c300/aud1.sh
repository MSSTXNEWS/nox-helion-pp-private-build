# AUD1: read-only audit of NOX self-awareness; prints only numbers, names, yes/no, md5
N=/workspace/nox; S=$N/state/core; NOW=$(date +%s)
age(){ [ -e "$1" ] && echo $(( (NOW-$(stat -c %Y "$1"))/3600 ))h || echo none; }
echo "AUD1 $(date +%F_%H:%M)"
echo "## chat_core live"
for f in $(find $N -name chat_core.py -not -path "*/archive/*" -not -path "*/node_modules/*" 2>/dev/null | head -5); do echo "$f md5=$(md5sum $f|cut -c1-8) lines=$(wc -l <$f) age=$(age $f)"; done
CC=$(find $N -name chat_core.py -not -path "*/archive/*" 2>/dev/null | head -1)
for k in "я сейчас" "self_now" "journal" "sensorium" "valence" "arousal" "cort" "board.mode" "control.vector|cvector" "RECALL_BEFORE" "s03_recall" "born_at" "genesis|ledger" "calibration|ece" "logprob" "последний разговор" "passport" "conscience" "chat_gate" "8793" "initiative|инициатив"; do echo "cc[$k]=$(grep -c -i -E "$k" $CC 2>/dev/null)"; done
echo "## flags off"; ls $N/state/*.off 2>/dev/null | xargs -n1 basename | tr '\n' ' '; echo
echo "## state/core files (name size age)"; for f in $S/* ; do [ -f "$f" ] && echo "$(basename $f) $(stat -c %s $f) $(age $f)"; done
echo "## state/mind"; for f in $N/state/mind/* ; do [ -f "$f" ] && echo "$(basename $f) $(stat -c %s $f) $(age $f)"; done
echo "## canon dir"; for f in $N/canon/*; do [ -f "$f" ] && echo "$(basename $f) $(stat -c %s $f) $(age $f)"; done
python3 -I - <<'PY'
import json,os,time,glob,collections
N="/workspace/nox"; S=N+"/state/core"; M=N+"/state/mind"
def L(p):
    try: return json.load(open(p,encoding="utf-8"))
    except Exception as e: return None
def typ(v): return type(v).__name__
sn=L(N+"/canon/sensorium.json")
print("## sensorium")
if sn is None: print("sensorium.json: absent/unreadable")
else:
    items=sn if isinstance(sn,list) else (sn.get("sensors") or sn.get("items") or [])
    if isinstance(items,dict): items=list(items.values())
    print("sensorium type=%s top_keys=%s n_sensors=%d"%(typ(sn),(list(sn.keys())[:12] if isinstance(sn,dict) else "-"),len(items)))
    ids=[i.get("id","") for i in items if isinstance(i,dict)]
    print("x_ext=%d with_metric=%d with_human=%d with_ai=%d"%(sum(1 for i in ids if str(i).startswith("x_")),sum(1 for i in items if isinstance(i,dict) and i.get("metric")),sum(1 for i in items if isinstance(i,dict) and i.get("human")),sum(1 for i in items if isinstance(i,dict) and i.get("ai"))))
    gr=collections.Counter(i.get("group") or i.get("g") or "?" for i in items if isinstance(i,dict)); print("groups=%d"%len(gr))
    mets=collections.Counter(str(i.get("metric","")).split("{")[0] for i in items if isinstance(i,dict)); print("distinct_metrics=%d"%len(mets))
sj=L(S+"/self_now.json"); print("## self_now keys:", list(sj.keys())[:30] if isinstance(sj,dict) else sj is None and "absent")
if isinstance(sj,dict) and "ts" in sj:
    try: print("self_now ts_age_s=%d"%(time.time()-float(sj["ts"])))
    except Exception: pass
hw=L(S+"/hardware.json"); print("hardware keys=%d"%(len(hw) if isinstance(hw,dict) else -1))
print("## journal")
p=S+"/journal.jsonl"
if os.path.exists(p):
    kinds=collections.Counter(); k24=collections.Counter(); n=0; last=0
    for l in open(p,encoding="utf-8",errors="ignore"):
        try: d=json.loads(l)
        except Exception: continue
        n+=1; k=str(d.get("kind","?")); kinds[k]+=1
        ts=d.get("ts")
        try:
            t=float(ts) if not isinstance(ts,str) else time.mktime(time.strptime(ts[:19].replace("T"," "),"%Y-%m-%d %H:%M:%S"))
        except Exception: t=0
        last=max(last,t)
        if t>time.time()-86400: k24[k]+=1
    print("lines=%d last_age_h=%.1f"%(n,(time.time()-last)/3600 if last else -1))
    print("kinds_all:",dict(kinds.most_common(30)))
    print("kinds_24h:",dict(k24.most_common(30)))
print("## passport")
pp=L(S+"/passport.json")
if pp is None: print("passport.json absent")
else:
    print("keys=%d:"%len(pp),list(pp.keys()))
    def walk(d,pre=""):
        out=[]
        if isinstance(d,dict):
            for k,v in d.items(): out+=walk(v,pre+"/"+k)
        else: out.append((pre,d))
        return out
    lv=walk(pp); hold=[a for a,b in lv if isinstance(b,str) and b.strip().upper().startswith("HOLD")]; empty=[a for a,b in lv if b in ("",None,[],{})]
    print("leaf_fields=%d hold=%d empty=%d filled=%d"%(len(lv),len(hold),len(empty),len(lv)-len(hold)-len(empty)))
    sr=pp.get("self_report"); print("self_report present=%s type=%s"%(sr is not None,typ(sr)))
    if isinstance(sr,dict): print("self_report keys:",list(sr.keys())[:10], "fields_n=%s"%(len(sr.get("fields",[])) if hasattr(sr.get("fields",[]),"__len__") else "?"))
    for k in ("owner_confirmed","approved","approved_by","filled_by","source","updated","version","born_at"):
        if k in pp: print("pp.%s present, type=%s"%(k,typ(pp[k])))
print("## born/genesis in jsons")
for f in glob.glob(S+"/*.json")+glob.glob(N+"/state/*.json"):
    d=L(f)
    if isinstance(d,dict):
        for k in d:
            if "born" in k.lower() or "genesis" in k.lower() or "stage" in k.lower() or "birth" in k.lower():
                v=d[k]; print("%s:%s type=%s null=%s"%(os.path.basename(f),k,typ(v),v is None))
print("## weekly_exam")
we=L(S+"/weekly_exam.json")
if isinstance(we,dict):
    print("keys:",list(we.keys())); 
    for k in ("score","score_measured_only","passed","measured","ts"):
        if k in we: print(k,"=",we[k])
    for r in we.get("rows",[]):
        v=r.get("value"); print(" row",r.get("test"),"pass=",r.get("pass"),"val=",v if isinstance(v,(int,float,bool)) or v is None else "str")
cal=L(M+"/calibration.json")
print("## calibration", {k:v for k,v in cal.items() if isinstance(v,(int,float))} if isinstance(cal,dict) else cal)
PY
echo "## ledger/genesis/birth files"; find $N -maxdepth 4 \( -iname "*genesis*" -o -iname "*ledger*" -o -iname "birth*" -o -iname "*born*" \) -not -path "*/archive/*" 2>/dev/null | head -20 | while read f; do echo "$f size=$(stat -c %s "$f") lines=$(wc -l <"$f" 2>/dev/null) age=$(age "$f")"; done
echo "birth_done=$([ -e $N/state/birth_done ] && echo 1||echo 0) birth_evidence=$([ -e $S/birth_evidence.json ] && echo 1||echo 0) conscience_test=$([ -e $S/conscience_test.json ] && echo 1||echo 0)"
echo "## sleep/dream/consolidation files"; find $N \( -path "*/archive" -o -path "*/node_modules" \) -prune -o -type f \( -iname "*sleep*" -o -iname "*nrem*" -o -iname "*dream*" -o -iname "*consolid*" -o -iname "*_rem*" -o -iname "*forget*" -o -iname "*morning*" -o -iname "*evening*" -o -iname "*initiat*" \) -print 2>/dev/null | head -40 | while read f; do echo "$f size=$(stat -c %s "$f") age=$(age "$f")"; done
echo "files modified last 24h in state (count): $(find $N/state -type f -mmin -1440 2>/dev/null | wc -l)"
echo "sleep-window (02-05) files mtime hour hist in state/core+mind:"; find $S $N/state/mind -type f -mmin -1440 -printf '%TH\n' 2>/dev/null | sort | uniq -c | tr '\n' ' '; echo
echo "## s03 recall"; ss -ltn 2>/dev/null | grep -o -E ":(18220|8300|8793|8104|8100|9100|8140|8141|8144)\b" | sort -u | tr '\n' ' '; echo
L=$N/state/s03_recall.log; [ -f $L ] && echo "recall_log lines=$(wc -l <$L) last24h_today=$(grep -c "^$(date +%H)" $L)" && awk '{for(i=1;i<=NF;i++) if($i ~ /^hits=/){split($i,a,"=");c[a[2]]++}} END{for(k in c) printf "hits[%s]=%d ",k,c[k]; print ""}' $L | cut -c1-300
echo "s03.db: $(find $N -name 's03*.db' -not -path '*/archive/*' 2>/dev/null | head -3 | while read f; do echo "$f size=$(stat -c %s $f) age=$(age $f)"; done)"
echo "## gate/judge"; for f in chat_gate.log chat_bo2.log chat_judgefix_stats.json; do p=$N/state/$f; [ -f $p ] && echo "$f lines=$(wc -l <$p) age=$(age $p)"; done
cat $N/state/chat_judgefix_stats.json 2>/dev/null | python3 -I -c "import sys,json;d=json.load(sys.stdin);print({k:v for k,v in d.items() if isinstance(v,(int,float,str)) and k in('day','judged','revised','advised')})" 2>/dev/null
[ -f $N/state/chat_gate.log ] && echo "gate_log_ok=$(grep -c ' ok' $N/state/chat_gate.log) nojudge=$(grep -c -i 'nojudge\|judge_err' $N/state/chat_gate.log) variants=$(grep -c -i 'variants' $N/state/chat_gate.log)"
echo "judge :8300 listening=$(ss -ltn 2>/dev/null | grep -c ':8300 ') gateway :8793 listening=$(ss -ltn 2>/dev/null | grep -c ':8793 ')"
echo "## control vectors / pad / neuro files"; find $N \( -path "*/archive" -o -path "*/node_modules" -o -path "*/.git" \) -prune -o -type f \( -iname "*cvec*" -o -iname "*control*vec*" -o -iname "*human_voice*" -o -iname "*ai_mind*" \) -print 2>/dev/null | head -10
for k in valence arousal neurochem "CORT" "dopamine|\bDA\b" "OXT"; do echo "grep_mods[$k]=$(grep -rlis -E "$k" $N/mods $N/canon $N/core $N/q26 --include=*.py --include=*.json 2>/dev/null | xargs -n1 basename 2>/dev/null | sort -u | tr '\n' ',')"; done
echo "## cycle"; echo "supervisor:"; supervisorctl status 2>/dev/null | awk '{print $1"="$2}' | tr '\n' ' '; echo
echo "cron lines: $(crontab -l 2>/dev/null | grep -v '^#' | grep -c .) ; mentions morning/evening/sleep in cron: $(crontab -l 2>/dev/null | grep -c -i -E 'morning|evening|sleep|dream')"
echo "inspector dir latest age: $(ls -t $N/state/inspector 2>/dev/null | head -1 | while read f; do age $N/state/inspector/$f; done); files=$(ls $N/state/inspector 2>/dev/null | wc -l)"
echo "tasks dir files=$(ls $N/state/tasks 2>/dev/null | wc -l)"
echo "mods present: $(ls $N/mods/*.py 2>/dev/null | xargs -n1 basename | tr '\n' ' ')"
echo "mods md5 vs: passport_self=$(md5sum $N/mods/passport_self.py 2>/dev/null|cut -c1-8) weekly_exam=$(md5sum $N/mods/weekly_exam.py 2>/dev/null|cut -c1-8) birth_ritual=$(md5sum $N/mods/birth_ritual.py 2>/dev/null|cut -c1-8)"
echo END
