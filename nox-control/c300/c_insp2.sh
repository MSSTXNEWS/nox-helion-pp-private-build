#!/bin/bash
# c_insp2: read-only search for pult/search/calendar/svc endpoints and client files
S=/workspace/nox/web/pkg/server; W=/workspace/nox/web/site
echo "== PY SERVER FILES"; ls $S/*.py | xargs -n1 basename | tr '\n' ' '; echo
echo "== ROUTE HITS (sleep/wake/priority/depth/voice/snapshot/backup/search/cal/svc/events)"
grep -n -i 'sleep\|wake\|priority\|depth\|snapshot\|backup\|/search\|cal/events\|/svc/\|events' $S/web_server.py | cut -c1-180 | head -60
echo "== OTHER MODULE ROUTES"
grep -l -i 'def _cal\|cal/events\|/search' $S/*.py 2>/dev/null
grep -n 'cal/events\|"/search\|/svc/' $S/*.py 2>/dev/null | cut -c1-160 | head -30
echo "== WEB SITE ROOT"; ls $W | head -80 | tr '\n' ' '; echo
echo "== NINJA/CMD FILES"; ls -la $W/nox-ninja.js $W/nox-cmd.js $W/qa/registry.json $W/qa/rework 2>&1 | head -20
echo "== STATE/WEB"; ls /workspace/nox/state/web 2>&1 | head -20
echo "== QA AUDIT HEAD"; head -c 600 /workspace/nox/qa_audit.py; echo
echo "== AUDIT.JSON KEYS"; python3 -I -c "import json;d=json.load(open('$W/qa/audit.json'));print({k:(v.get('status'),v.get('wow')) for k,v in d.items()})" 2>&1 | head -c 1200; echo
echo "== DISK"; df -BG / | tail -1
