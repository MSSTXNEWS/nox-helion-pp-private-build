#!/bin/bash
S=/workspace/nox/web/site; P=/workspace/nox/web/pkg/server; PY=/workspace/nox/venv/bin/python; T=bak_s3_10
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
curl -fsSL "$RAW/s3_patch_cc4.py?v=$(date +%s)" -o /tmp/s3cc4.py || exit 1
cp $P/chat_core.py $P/chat_core.py.$T; cp $P/nox_cmd.py $P/nox_cmd.py.$T; cp $S/nox-persona.js $S/nox-persona.js.$T; cp $S/qa/registry.json $S/qa/registry.json.$T
rollback(){ echo ROLLBACK; cp $P/chat_core.py.$T $P/chat_core.py; cp $P/nox_cmd.py.$T $P/nox_cmd.py; cp $S/nox-persona.js.$T $S/nox-persona.js; cp $S/qa/registry.json.$T $S/qa/registry.json; $P/run_web.sh restart >/dev/null 2>&1; }
$PY -I /tmp/s3cc4.py && $PY -m py_compile $P/chat_core.py $P/nox_cmd.py || { rollback; exit 1; }
(cd $P && $PY -c "import chat_core;print('prefix',chat_core._persona_prefix())" 2>&1 | tail -2)
$P/run_web.sh restart >/tmp/s3_restart_cc4.log 2>&1; sleep 4
c=$(curl -s -m 5 -o /dev/null -w '%{http_code}' localhost:8091/api/chat/health); [ "$c" = 200 ] || { rollback; exit 1; }
echo "T chat one message:"; curl -s -m 100 -X POST localhost:8091/api/chat -H 'Content-Type: application/json' -d '{"conversation_id":"s3persona","message":"Ответь одним словом: тест"}' | head -c 700; echo
echo "T health after $(curl -s -m 5 -o /dev/null -w '%{http_code}' localhost:8091/api/chat/health)"
post(){ curl -s -m 15 -X POST localhost:8091/api/cmd -H 'Content-Type: application/json' -d "$1" | head -c 400; echo; }
echo "T persona.get:"; post '{"name":"persona.get","params":{}}'
echo "T restart step1:"; post '{"name":"svc.restart","params":{"service":"navidrome"}}'
echo "-- confirm code"; grep -n "confirm" $P/web_server.py | cut -c1-220 | head -12
$PY /workspace/nox/qa_ctl.py --pin
