#!/bin/bash
Q=/workspace/nox/web/site/qa
echo "FIXED:"; ls -lt --time-style=+%H:%M $Q/rework/*.fixed 2>/dev/null
echo "RECENT:"; ls -lt --time-style=+%H:%M $Q/rework/*.json | head -6
python3 - <<'P'
import json
a=json.load(open('/workspace/nox/web/site/qa/audit.json'))
for k,v in sorted(a.items()): print(k,v['status'],v.get('wow'),v.get('ARU'),v.get('cycle'),v['ts'][11:16])
P
tail -3 /workspace/nox/agent/out/qa_audit.log | cut -c1-160; date +%H:%M
