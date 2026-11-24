RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
curl -fsSL "$RAW/qa_audit.py?y" -o /workspace/nox/qa_audit.py
F=/workspace/nox/web/pkg/server/web_server.py
sed -i 's|except Exception as e: data=_j.dumps({"error":str(e)}).encode(); code=503|except Exception as e: data=_j.dumps({"ok":False,"error":str(e)[:200]}).encode(); code=200|' $F
python3 -m py_compile $F && /workspace/nox/web/pkg/server/run_web.sh restart >/dev/null 2>&1
python3 -c "
import json;r=json.load(open('/workspace/nox/web/site/qa/report.json'))
from collections import Counter;c=Counter((vp,x.split(':')[0][:40]) for p in r['pages'].values() for vp,l in p.items() for x in l);print(c.most_common(10))
print({k:v for k,v in list(r['pages'].items())[:2]})" | cut -c1-1500
rm -f /workspace/nox/web/site/qa/audit.json; echo ok
