#!/bin/bash
S=/workspace/nox/web/site; P=/workspace/nox/web/pkg/server; T=bak_s3_5
RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300
PY=/workspace/nox/venv/bin/python
cd /tmp
for f in s3_cmd_patch.py nox-actions.js nox-cast-btn.js nox-radial.js nox-live.js nox-gesture.js; do curl -fsSL "$RAW/$f?v=$(date +%s)" -o /tmp/s3srv_$f || { echo "FETCH FAIL $f"; exit 1; }; done
# --- сервер: бэкап, патч, компиляция, рестарт, тест, откат
cp $P/nox_cmd.py $P/nox_cmd.py.$T; cp $S/qa/registry.json $S/qa/registry.json.$T
$PY /tmp/s3srv_s3_cmd_patch.py && $PY -m py_compile $P/nox_cmd.py && echo compiled
rollback(){ echo ROLLBACK; cp $P/nox_cmd.py.$T $P/nox_cmd.py; cp $S/qa/registry.json.$T $S/qa/registry.json; $P/run_web.sh restart >/dev/null 2>&1; }
if ! $PY -m py_compile $P/nox_cmd.py; then rollback; exit 1; fi
$P/run_web.sh restart >/tmp/s3_restart.log 2>&1
ok=0; for i in $(seq 1 20); do c=$(curl -s -m 4 -o /dev/null -w '%{http_code}' localhost:8091/api/chat/health); [ "$c" = 200 ] && ok=1 && break; sleep 3; done
[ $ok = 1 ] || { echo "health not 200 after restart"; rollback; exit 1; }
echo "health 200"
post(){ curl -s -m 15 -X POST localhost:8091/api/cmd -H 'Content-Type: application/json' -d "$1" | head -c 220; echo; }
echo T-state;  post '{"name":"ui.state","params":{}}'
echo T-volume; post '{"name":"volume","params":{"level":0.8}}'
echo T-projector; post '{"name":"projector","params":{"on":false}}'
echo T-focus; post '{"name":"focus","params":{"on":false}}'
echo T-notify; post '{"name":"notify.test","params":{}}'
echo T-restart-no-token; post '{"name":"svc.restart","params":{"service":"web"}}'
echo T-unknown; post '{"name":"rm.rf","params":{}}'
c=$(curl -s -m 5 -o /dev/null -w '%{http_code}' localhost:8091/api/chat/health); [ "$c" = 200 ] || { rollback; exit 1; }
# --- клиент
for f in nox-actions.js nox-cast-btn.js nox-radial.js nox-live.js nox-gesture.js; do [ -f $S/$f.$T ] || { [ -f $S/$f ] && cp $S/$f $S/$f.$T; }; cp /tmp/s3srv_$f $S/$f && echo placed $f; done
n=0; for f in $S/*.html; do grep -q "nox-pult.js" $f || continue; grep -q 'nox-radial.js' $f || { sed -i 's#</body>#<script src="./nox-radial.js" defer></script><script src="./nox-live.js" defer></script><script src="./nox-gesture.js" defer></script>\n</body>#' $f; n=$((n+1)); }; done; echo "client injected $n"
# --- модель жестов MediaPipe
M=$S/vendor/mediapipe-tasks-vision/hand_landmarker.task
[ -s $M ] || curl -fsSL -m 90 -o $M https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task && echo "model ok $(stat -c %s $M)" || echo "model download FAILED"
# --- Meilisearch
echo meili: $(curl -s -m 4 localhost:7700/health); echo "search via /search:"; curl -s -m 8 "localhost:8091/search?q=память" | head -c 200; echo
$PY /workspace/nox/qa_ctl.py --pin
echo "- $(date +%F) S3: команды ui.state/volume/projector/focus/notify.test/svc.restart(web, confirm) в nox_cmd.py + registry; радиальное меню, ambient-проектор (Wake Lock), живые обои от live.json, жесты MediaPipe (нужна модель). Бэкапы *.bak_s3_5" >> /workspace/nox/PROGRESS.md
