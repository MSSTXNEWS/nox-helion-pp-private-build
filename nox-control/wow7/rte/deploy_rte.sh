#!/usr/bin/env bash
# RTE-05: развёртывание rte_server на S1 (:8084). Запуск: bash deploy_rte.sh [--dry-run]
# Берёт файлы из репо (nox-control/wow7/rte/) через raw.githubusercontent.com (main), гоняет unittest, стартует сервер, пишет /root/nox/receipts/RTE-05.json
set -u
DRY=0; [ "${1:-}" = "--dry-run" ] && DRY=1
RAW="${RTE_RAW:-https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/wow7/rte}"
DST="${RTE_DST:-/root/nox/src/rte}"
REC="${NOX_RECEIPTS_DIR:-/root/nox/receipts}"
FILES="aio.py router.py stream_hub.py stop.py bridge_intro.py rte_server.py fakes.py test_rte.py probe_pv01.py"
log(){ echo "[RTE-05] $*"; }
run(){ if [ "$DRY" = 1 ]; then log "dry-run: $*"; else eval "$@"; fi; }
run "mkdir -p '$DST' '$REC' /root/nox/state/rte /root/nox/logs"
for f in $FILES; do run "curl -fsS --retry 3 -o '$DST/$f' '$RAW/$f'" || { log "fail download $f"; exit 2; }; done
if [ "$DRY" = 1 ]; then log "dry-run: cd $DST && python3 -m unittest test_rte"; else
  (cd "$DST" && python3 -m unittest test_rte >/root/nox/logs/rte_unittest.log 2>&1) || { log "unittest FAIL, см. /root/nox/logs/rte_unittest.log"; exit 3; }
fi
run "pkill -f 'rte_server.py' || true"
run "cd '$DST' && NOX_GATEWAY_URL=http://127.0.0.1:8082 NOX_DEEP_SLOTS_URL=http://127.0.0.1:8081 NOX_FAST_UPSTREAM=http://127.0.0.1:8083 nohup setsid python3 rte_server.py >>/root/nox/logs/rte.log 2>&1 < /dev/null &"
OK=false
if [ "$DRY" = 0 ]; then sleep 2; curl -fsS http://127.0.0.1:8084/v1/rte/health >/dev/null 2>&1 && OK=true; else OK=dry-run; fi
if [ "$DRY" = 0 ]; then printf '{"id":"RTE-05","ok":%s,"ts":"%s","dst":"%s"}\n' "$OK" "$(date -u +%FT%TZ)" "$DST" > "$REC/RTE-05.json"; fi
log "done ok=$OK"
[ "$OK" = true ] || [ "$OK" = dry-run ]
