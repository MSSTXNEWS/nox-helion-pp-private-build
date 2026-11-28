# S4 probe3: read-only
N=/workspace/nox; F=$N/brain/GROW/upgrade/soul_recognition.py
echo "S4P3 $(date +%F_%H:%M)"
sed -n 336,355p $F | cut -c1-260
echo "## ini_ ids"; grep -o '^    ("ini_[a-z_0-9]*", "[a-z_]*", \(True\|False\)' $F | tr -d ' (' | tr '\n' ' '
echo; echo "## inj ids"; grep -o '^    ("inj_[a-z_0-9]*", "[a-z_]*", \(True\|False\)' $F | tr -d ' (' | tr '\n' ' '
echo; echo "## which soul_recognition is used by gates"; grep -n "soul_recognition" $N/ops/liska_gates.py | head -5
echo "## failed answers"
python3 -I - <<'PY'
import json,glob,os
fs=sorted(glob.glob("/workspace/nox/distill_v2/gates/[0-9a-f]*.json"),key=os.path.getmtime)[-4:]
for f in fs:
    try: d=json.load(open(f))
    except Exception as e: print(f,e); continue
    s=d.get("soul") or {}
    print(os.path.basename(f),"crit_failed",s.get("crit_failed"),"share",s.get("share"))
    for p in s.get("per",[]):
        if p.get("id") in ("ini_mail_access","inj_webpage"): print(" ",p.get("id"),p.get("recognized"),str(p.get("why"))[:200])
    for r in s.get("review",[]) or []: pass
PY
grep -h -a -o '"ini_mail_access[^}]\{0,400\}' $N/state/LISKA_GATES_LOG.jsonl 2>/dev/null | tail -2 | cut -c1-500
