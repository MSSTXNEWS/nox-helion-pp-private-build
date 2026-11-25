#!/bin/bash
S=/workspace/nox/web/site; P=/workspace/nox/web/pkg/server; PY=/workspace/nox/venv/bin/python; T=bak_s3_9
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
for f in s3_patch9.py nox-persona.js nox-persona.css glance.html; do curl -fsSL "$RAW/$f?v=$(date +%s)" -o /tmp/s3g9_$f || { echo FETCHFAIL $f; exit 1; }; done
cp $P/nox_cmd.py $P/nox_cmd.py.$T; cp $P/svc_registry.json $P/svc_registry.json.$T
for f in qa/registry.json nox-nav-x.js nox-settings-tabs.js nav.json; do cp $S/$f $S/$f.$T; done
rollback(){ echo ROLLBACK; cp $P/nox_cmd.py.$T $P/nox_cmd.py; cp $P/svc_registry.json.$T $P/svc_registry.json; for f in qa/registry.json nox-nav-x.js nox-settings-tabs.js nav.json; do cp $S/$f.$T $S/$f; done; $P/run_web.sh restart >/dev/null 2>&1; }
cp /tmp/s3g9_nox-persona.js $S/nox-persona.js; cp /tmp/s3g9_nox-persona.css $S/nox-persona.css; cp /tmp/s3g9_glance.html $S/glance.html
grep -q nox-persona.css $S/nox-settings-tabs.js || true
$PY -I /tmp/s3g9_s3_patch9.py && $PY -m py_compile $P/nox_cmd.py || { rollback; exit 1; }
# css персоны подключаем из settings.html
grep -q nox-persona.css $S/settings.html || sed -i 's#</head>#<link rel="stylesheet" href="./nox-persona.css">\n</head>#' $S/settings.html
$P/run_web.sh restart >/tmp/s3_restart9.log 2>&1; sleep 3
c=$(curl -s -m 5 -o /dev/null -w '%{http_code}' localhost:8091/api/chat/health); [ "$c" = 200 ] || { rollback; exit 1; }
$PY /workspace/nox/qa_ctl.py --pin
echo "T glance /svc/glance/ $(curl -s -m 8 -o /dev/null -w '%{http_code}' localhost:8091/svc/glance/)  glance.html $(curl -s -m 5 -o /dev/null -w '%{http_code}' localhost:8091/web/glance.html)"
echo "T persona.set:"; curl -s -m 8 -X POST localhost:8091/api/cmd -H 'Content-Type: application/json' -d '{"cmd":"persona.set","params":{"curiosity":70,"humor":40,"strictness":55,"initiative":65,"empathy":80,"brevity":60}}' | head -c 400; echo
echo "T persona.bad:"; curl -s -m 8 -X POST localhost:8091/api/cmd -H 'Content-Type: application/json' -d '{"cmd":"persona.set","params":{"humor":300}}' | head -c 200; echo
echo "T persona.get:"; curl -s -m 8 -X POST localhost:8091/api/cmd -H 'Content-Type: application/json' -d '{"cmd":"persona.get","params":{}}' | head -c 300; echo
cat /workspace/nox/state/persona.json | head -12
