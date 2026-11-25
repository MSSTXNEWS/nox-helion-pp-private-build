echo "C300: u_recon2"
S=/workspace/nox/web/site; cd $S
ls /workspace/nox/state/mock_qa 2>&1 | head; grep -n "mock_qa\|allow_image" /workspace/nox/qa_audit.py | head -8
ls vendor | grep -iE "ninja|gridstack|motion|echarts|auto-animate|view-trans|chart" 
grep -c "" nox-tools.js; grep -o "NOXTools[A-Za-z.]*\|window\.[A-Za-z]*=" nox-tools.js | sort | uniq -c | sort -rn | head -8; grep -l "nox-tools.js" *.html | wc -l; grep -o "nox-tools.js[^\"']*" index.html | head -2
head -c 600 nox-tools.js
echo; for e in train/status hunger system/live ledger inspector; do echo "== $e"; curl -s -m5 http://127.0.0.1:18230/$e | head -c 500; echo; done
grep -n "p3st\|advgw" /workspace/nox/web/pkg/server/svc_registry.json | head; python3 -c "
import json;d=json.load(open('/workspace/nox/web/pkg/server/svc_registry.json'));print(type(d),list(d)[:3] if isinstance(d,dict) else d[:1]);print(json.dumps(d.get('advgw') or [x for x in d if 'advgw' in json.dumps(x)][:1])[:300])"
grep -c "" system.html; grep -o "<script[^>]*src=[^>]*>" system.html | head -20; grep -c echarts system.html
