echo "C300: ui_g5"; for p in index creative settings; do echo "== $p"; tail -c 1500 /workspace/nox/agent/out/ui_q2_$p.out 2>&1; done; python3 - <<'P'
import json
try:
    d=json.load(open('/workspace/nox/web/site/qa/audit.json'))
    for k in ('index','creative','settings'):
        v=d.get(k) or d.get(k+'.html') or (d.get('pages') or {}).get(k); print(k,json.dumps(v,ensure_ascii=False)[:600])
except Exception as e: print('audit.json',e)
P
