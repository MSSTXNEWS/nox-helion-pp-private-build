#!/bin/bash
S=/workspace/nox/web/site
echo "### cmp"; cmp /workspace/nox/qa_audit.py /workspace/nox/nox-control/c300/qa_audit.py 2>&1 | head -2; ls -la $S/qa/rework/*.fixed
python3 - <<'P'
import json
r=json.load(open('/workspace/nox/web/site/qa/registry.json'))
for k,v in r['sections'].items(): print(k, v.get('name'), '|', v.get('top10_refs'), '|', v.get('markers'), '|', v.get('commands'))
for k,v in r['commands'].items(): print('CMD',k,{a:b for a,b in v.items() if a!='cmd'})
P
echo "### nox_cmd"; f=$(python3 -c "import sys;sys.path.insert(0,'/workspace/nox/web/pkg/server');import nox_cmd;print(nox_cmd.__file__)"); echo $f; wc -l $f; grep -n "confirm\|cmd_log\|60" $f | head -20
echo "### nox-cmd.js"; wc -c $S/nox-cmd.js; head -c 700 $S/nox-cmd.js
echo "### cmdlog"; tail -3 /workspace/nox/state/cmd_log.jsonl
echo "### test"; for b in '{"name":"health"}' '{"name":"zzz"}'; do curl -s -w " %{http_code}\n" -X POST -H 'Content-Type: application/json' -d "$b" http://127.0.0.1:8091/api/cmd | cut -c1-200; done
echo "### auditlog"; tail -8 /workspace/nox/agent/out/qa_audit.log | cut -c1-300
echo "### S state"; ls -la --time-style=+%H:%M $S/*.html | sort -k6 | tail -12 | awk '{print $6,$7}'; ls /workspace/nox/web/site/qa/rework/
grep -n "PINNED\|pin" /workspace/nox/qa_ctl.py | head -5; ls /workspace/nox/state/*.json 2>/dev/null | head; grep -rn "События" $S/nox-events.js 2>/dev/null | head -2; ls $S | grep -i event
