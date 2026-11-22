#!/usr/bin/env bash
# TOP-01/02/03: установка eval_top.py на S1, тесты, базовый прогон, опц. ночной cron.
# Использование: deploy_top.sh [--dry-run] [--url URL] [--run] [--cron] [--only a,b]
set -euo pipefail
DRY=0; URL="${NOX_GATEWAY_URL:-http://127.0.0.1:8082}"; RUN=0; CRON=0; ONLY=""
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
LOGS="${NOX_LOGS:-/root/nox/logs}"
DEST="${NOX_SRC:-/root/nox/src}/top"; STATE="${NOX_STATE:-/root/nox/state}"; REC="${NOX_RECEIPTS:-/root/nox/receipts}"
while [ $# -gt 0 ]; do case "$1" in
  --dry-run) DRY=1;; --run) RUN=1;; --cron) CRON=1;;
  --url) URL="$2"; shift;; --only) ONLY="$2"; shift;;
  *) echo "неизвестный аргумент: $1" >&2; exit 64;; esac; shift; done
say() { echo "[TOP] $*"; }
do_() { if [ "$DRY" = 1 ]; then say "dry-run: $*"; else eval "$@"; fi; }
for f in eval_top.py test_eval_top.py; do [ -f "$SRC_DIR/$f" ] || { echo "нет $f" >&2; exit 66; }; done
do_ "mkdir -p '$DEST' '$STATE' '$REC' '$LOGS'"
do_ "cp '$SRC_DIR/eval_top.py' '$SRC_DIR/test_eval_top.py' '$DEST/'"
TESTS=skipped; RC=skipped
if [ "$DRY" = 0 ]; then
  (cd "$DEST" && python3 -m unittest test_eval_top >$LOGS/top_tests.log 2>&1) && TESTS=ok || { TESTS=fail; say "тесты упали, см. $LOGS/top_tests.log"; }
fi
EXTRA=""; [ -n "$ONLY" ] && EXTRA="--only $ONLY"
if [ "$RUN" = 1 ]; then
  if [ "$DRY" = 1 ]; then say "dry-run: python3 $DEST/eval_top.py --url $URL --json $STATE/eval_top_$(date +%F).json $EXTRA"; RC=dry
  else
    set +e; python3 "$DEST/eval_top.py" --url "$URL" --json "$STATE/eval_top_$(date +%F).json" $EXTRA | tee $LOGS/top_eval.log
    RC=${PIPESTATUS[0]}; set -e
    cp "$STATE/eval_top_$(date +%F).json" "$STATE/eval_top_last.json" 2>/dev/null || true
  fi
fi
if [ "$CRON" = 1 ]; then
  LINE="17 4 * * * python3 $DEST/eval_top.py --url $URL --json $STATE/eval_top_\$(date +\\%F).json >>$LOGS/top_eval.log 2>&1 # TOP-03"
  if [ "$DRY" = 1 ]; then say "dry-run: crontab += $LINE"
  else ( crontab -l 2>/dev/null | grep -v '# TOP-03' || true; echo "$LINE" ) | crontab -; fi
fi
if [ "$DRY" = 1 ]; then say "dry-run: квитанция $REC/TOP-01.json не пишется"; exit 0; fi
OK=false; [ "$TESTS" = ok ] && OK=true
printf '{"id":"TOP-01","ok":%s,"tests":"%s","eval_rc":"%s","url":"%s","ts":%s}\n' "$OK" "$TESTS" "$RC" "$URL" "$(date +%s)" > "$REC/TOP-01.json"
say "квитанция $REC/TOP-01.json ok=$OK"; [ "$OK" = true ]
