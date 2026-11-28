echo "K1: q27_gw3"
export RUNNER_TRACKING_ID=""
G=/workspace/nox/advisors/gateway.py; N=/workspace/nox
E=$(grep -nE "^ENV *=|ENV *= " $G | head -2 | sed -E 's/(gsk_|AIza|csk-)[A-Za-z0-9_-]+/KEY/g'); echo "ENV def: $E"
EP=$(python3 - <<'PY'
import re
s=open("/workspace/nox/advisors/gateway.py",encoding="utf-8").read()
m=re.search(r"^ENV\s*=\s*(.+)$",s,re.M); print(m.group(1)[:120] if m else "")
PY
); echo "ENV expr: $EP" | sed -E 's#/workspace/nox#N#'
python3 - <<'PY'
import re,os
s=open("/workspace/nox/advisors/gateway.py",encoding="utf-8").read()
ns={"os":os}
m=re.search(r"^ST\s*=\s*(.+)$",s,re.M); e=re.search(r"^ENV\s*=\s*(.+)$",s,re.M)
try:
    exec("ST="+m.group(1),ns); exec("ENV="+e.group(1),ns); p=ns["ENV"]
except Exception as x: print("evalfail",type(x).__name__); raise SystemExit
print("env file exists",os.path.exists(p),"size",os.path.getsize(p) if os.path.exists(p) else 0,"name",os.path.basename(p))
names=["GROQ_API_KEY","CEREBRAS_API_KEY","GEMINI_API_KEY","OPENROUTER_API_KEY","MISTRAL_API_KEY","GITHUB_MODELS_TOKEN","KILO_API_KEY","LLM7_API_KEY"]
d={}
for ln in open(p,errors="replace"):
    ln=ln.strip()
    if ln and not ln.startswith("#") and "=" in ln:
        k,v=ln.split("=",1); d[k.strip()]=bool(v.strip().strip("\"'"))
for n in names: print(n,"SET" if d.get(n) else "no")
print("other_keys_count",len([k for k in d if k not in names]))
PY
echo "--- 4210 service"; grep -rlE "4210" $N/supervisor $N/state/*.json /home/claude/brain/supervisor 2>/dev/null | head -5
ls /workspace/nox | grep -iE "litellm|proxy|gw|free" | head; which litellm 2>&1 | head -1; python3 -c "import litellm;print('litellm',litellm.__version__ if hasattr(litellm,'__version__') else 'ok')" 2>&1 | tail -1
ps -eo args | grep -iE "litellm|:4210|4210" | grep -v grep | cut -c1-120 | sed -E 's/(gsk_|AIza|csk-)[A-Za-z0-9_-]+/KEY/g'
grep -n "4210" $G | head -3 | cut -c1-140
find $N -maxdepth 3 \( -name "*4210*" -o -name "free_proxy*" -o -name "keyless*" -o -name "*anon_gw*" \) 2>/dev/null | head -5
journalctl -u '*4210*' --no-pager -n 3 2>/dev/null | wc -l
echo END
