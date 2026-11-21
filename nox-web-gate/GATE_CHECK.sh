#!/bin/bash
# «Ворота»: статический сервер + настоящий gateway.py + поддельный llama-server + Playwright e2e. Код выхода 0 только если всё прошло.
set -u
cd "$(dirname "$0")"
export NODE_PATH="$(npm root -g)"
export GATE_ROOT="$(pwd)"
for p in 8082 18081 18082 18083 18790; do
  if (exec 3<>/dev/tcp/127.0.0.1/$p) 2>/dev/null; then echo "GATE: порт $p занят, остановите процесс и повторите" >&2; exit 2; fi
done
node ./GATE_CHECK.js "$@"
rc=$?
echo "GATE exit=$rc (отчёт: $GATE_ROOT/GATE_REPORT.md)"
exit $rc
