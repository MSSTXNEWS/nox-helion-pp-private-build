#!/bin/bash
S=/workspace/nox/web/site
cd $S
echo "#### reg cmds"; /workspace/nox/venv/bin/python - <<'P'
import json
r=json.load(open('/workspace/nox/web/site/qa/registry.json'))
print(list(r.keys()))
for k,v in r['commands'].items(): print(k,v)
print({k:(v['name'],v.get('commands')) for k,v in r['sections'].items()})
print('checklist' in r, str(r.get('checklist'))[:200])
P
echo "#### dock where"; grep -ln "КИНОТЕАТР" *.js *.html | head; grep -n "КИНОТЕАТР" nox-*.js | cut -c1-300 | head
echo "#### routes"; grep -n 'p == "/\|p in ("/\|p.startswith("/api' /workspace/nox/web/pkg/server/web_server.py | cut -c1-160 | head -80
echo "#### audit"; grep -n "NICHE\|^REG\|checklist\|def " /workspace/nox/qa_audit.py | cut -c1-200 | head -60
echo "#### qa_ctl"; grep -n "pin\|def " /workspace/nox/qa_ctl.py | cut -c1-160 | head -30
echo "#### dockhtml"; grep -o 'nxdock[^"]\{0,60\}' index.html | head -3; grep -n "nxd-cells" nox-dock*.js | cut -c1-260 | head -8
echo "#### nav-x"; head -c 1500 nox-nav-x.js
echo "#### sleep?"; ls /workspace/nox/web/pkg/server/*.py | head -30; grep -rn "sleep\|priority\|pause" /workspace/nox/web/pkg/server/web_server.py | cut -c1-140 | head
