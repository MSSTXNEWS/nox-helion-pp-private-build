echo "C300: tr_recon5"
cd /workspace/nox
curl -s -m5 localhost:8300/judges | python3 -c "
import json,sys
d=json.load(sys.stdin)
for k,v in d.items(): print(k,'|',v.get('kind'),'|',v.get('topic'),'|',v.get('status'),'|',v.get('device'),'|',v.get('mode'))"
F=judges/judge_service.py; wc -l $F
grep -n "class .*BaseModel\|@app\.\(post\|get\)\|^def \|^async def " $F | cut -c1-150 | head -60
echo ---judge endpoint; awk '/@app.post\("\/judge"/,/^@app.post\("\/embed"/' $F | head -70 | cut -c1-220
echo "== guard_svc"; wc -l svc/pipeline/guard_svc.py; sed -n 1,80p svc/pipeline/guard_svc.py | cut -c1-200
echo "== guard on 8300 judges: injection models"; ls models/guard models/gpu 2>/dev/null | head -50
echo END
