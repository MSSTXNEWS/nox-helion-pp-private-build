echo "C300: ac_mb5"
F=/workspace/nox/distill_v2/code/distill_v2.py
grep -n "tok-budget" $F | cut -c1-200
cat /workspace/nox/state/tok_budget_max 2>&1 | head -2
python3 -c "
import json,glob
for f in glob.glob('/workspace/nox/state/*.json'):
    try: d=json.load(open(f))
    except Exception: continue
    if isinstance(d,dict) and any('tok_budget' in k for k in d): print(f,{k:v for k,v in d.items() if 'tok_budget' in k})
" | cut -c1-500
sed -n 2020,2040p $F | cut -c1-210
grep -an "tok_budget\|бюджет" /workspace/nox/agent/autotrain/rounds/r038/train.log | head -5 | cut -c1-250
