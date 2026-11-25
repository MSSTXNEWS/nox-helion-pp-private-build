#!/bin/bash
S=/workspace/nox/web/site
echo "### qa dir"; ls -la $S/qa | head -40; ls $S/qa/rework 2>/dev/null
echo "### registry"; python3 -c "
import json;r=json.load(open('$S/qa/registry.json'));print(list(r.keys()));print(len(r.get('sections',{})),len(r.get('commands',{})),len(r.get('checklist',[])))" 2>&1
echo "### qa_audit diff vs c300"; ls -la /workspace/nox/qa_audit.py; head -c 600 /workspace/nox/qa_audit.py
echo "### cmd route"; grep -n "api/cmd\|cmd_log\|confirm_token" /workspace/nox/web/pkg/server/web_server.py | head; ls $S/nox-cmd.js 2>&1
echo "### loop"; ps aux | grep -E "qa_audit|qa_ctl" | grep -v grep | cut -c1-200; cat /workspace/nox/qa_audit_loop.sh 2>&1 | head -30
echo "### audit.json"; python3 -c "
import json;a=json.load(open('$S/qa/audit.json'))
for k,v in a.items(): print(k,v.get('status'),v.get('wow'),v.get('ARU'),v.get('cycle'),v.get('ts'))" 2>&1
echo "### health"; curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8091/api/chat/health
ls $S/*.html | wc -l; ls $S/*.html | xargs -n1 basename | tr '\n' ' '
echo; ls /workspace/nox/state | head -20; df -h /workspace | tail -1
