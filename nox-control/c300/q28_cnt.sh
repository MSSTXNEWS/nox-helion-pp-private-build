echo "K1: q28_cnt"
export RUNNER_TRACKING_ID=""
python3 - <<'PY'
import glob,json,re,collections,os,time
W=os.environ.get("NOX_WEB_STATE") or ""
cands=[W,"/workspace/nox/state/web","/workspace/nox/web/state","/workspace/nox/state/web_conv"]
dirs=[d for d in cands if d and os.path.isdir(d)]
print("dirs",[d.replace("/workspace/nox/","N/") for d in dirs])
pats={"drift":re.compile(r"не сложился|сбой черновика"),"slow":re.compile(r"отвечаю медленно"),"judge":re.compile(r"не прошёл проверку судей|судьи сейчас недоступны"),"busy":re.compile(r"модель сейчас занята и не успела"),"messir":re.compile(r"(?i)\bмессир"),"creator":re.compile(r"(?i)\bсоздател")}
now=time.time(); tot=collections.Counter(); byday=collections.defaultdict(collections.Counter)
for d in dirs:
    for f in glob.glob(d+"/**/*.json",recursive=True):
        try: c=json.load(open(f))
        except Exception: continue
        if not isinstance(c,dict) or not isinstance(c.get("messages"),list): continue
        qa=os.path.basename(f).startswith("qa-") or str(c.get("id","")).startswith(("qa-","rv-"))
        for m in c["messages"]:
            if m.get("role")!="assistant": continue
            a=str(m.get("content") or ""); ts=m.get("ts") or 0
            day=time.strftime("%m-%d",time.localtime(ts)) if ts else "?"
            k="qa" if qa else "real"
            byday[(day,k)]["n"]+=1
            for n,r in pats.items():
                if r.search(a): byday[(day,k)][n]+=1
for (day,k),c in sorted(byday.items())[-14:]: print(day,k,dict(c))
PY
echo "fast_ok flag files: $(ls /workspace/nox/state/chat_fast.off 2>&1 | tail -1) owner_active_age_s=$(( $(date +%s) - $(stat -c %Y /workspace/nox/state/orch/OWNER_ACTIVE 2>/dev/null || echo 0) ))"
echo "race/pipe flags: $(python3 -c "import json;d=json.load(open('/workspace/nox/state/core/persona.json'));print(d.get('living_engines'))" 2>&1 | cut -c1-200)"
echo END
