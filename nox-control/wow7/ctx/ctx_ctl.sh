#!/usr/bin/env bash
# ctx_ctl.sh: установка и самопроверка модулей CTX. Команды: install | selftest | idle-once | status. Флаг --dry-run ничего не пишет.
# Квитанция: $RECEIPTS/CTX-<cmd>.json (по умолчанию /root/nox/receipts). Пути переопределяются: DEST, RECEIPTS, STATE.
set -u
CMD="${1:-}"; shift || true
DRY=0; for a in "$@"; do [ "$a" = "--dry-run" ] && DRY=1; done
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${DEST:-/root/nox/src/nox-control/wow7/ctx}"
RECEIPTS="${RECEIPTS:-/root/nox/receipts}"
STATE="${STATE:-/root/nox/state/ctx}"
FILES="ctxcommon.py summarizer.py context_manager.py idle_precompute.py loss_eval.py test_ctx.py"
say() { printf '%s\n' "$*"; }
receipt() { # $1=id $2=ok(true|false) $3=detail
  [ "$DRY" = 1 ] && { say "[dry-run] квитанция $RECEIPTS/$1.json ok=$2 $3"; return; }
  mkdir -p "$RECEIPTS"
  printf '{"id":"%s","ok":%s,"detail":"%s","ts":%s}\n' "$1" "$2" "$3" "$(date +%s)" > "$RECEIPTS/$1.json"
}
case "$CMD" in
  install)
    for f in $FILES; do [ -f "$HERE/$f" ] || { say "нет файла $f"; receipt CTX-install false "missing $f"; exit 2; }; done
    if [ "$DRY" = 1 ]; then say "[dry-run] mkdir -p $DEST $STATE; cp $FILES -> $DEST"; receipt CTX-install true dry; exit 0; fi
    mkdir -p "$DEST" "$STATE" && for f in $FILES; do cp "$HERE/$f" "$DEST/$f"; done || { receipt CTX-install false "copy failed"; exit 3; }
    if (cd "$DEST" && python3 -B test_ctx.py >/tmp/ctx_test.log 2>&1); then receipt CTX-install true "tests ok"; say "OK: установлено в $DEST, тесты зелёные"
    else receipt CTX-install false "tests failed: /tmp/ctx_test.log"; tail -20 /tmp/ctx_test.log; exit 4; fi ;;
  selftest)
    if [ "$DRY" = 1 ]; then say "[dry-run] python3 -B $HERE/test_ctx.py"; receipt CTX-selftest true dry; exit 0; fi
    if (cd "$HERE" && python3 -B test_ctx.py >/tmp/ctx_test.log 2>&1); then receipt CTX-selftest true ok; say OK; else receipt CTX-selftest false failed; tail -20 /tmp/ctx_test.log; exit 4; fi ;;
  idle-once)
    : "${SOUL:=/root/nox/state/soul_prompt_ru.txt}"
    ARGS=(--db "$STATE/turns.sqlite" --state "$STATE/state.json" --soul "$SOUL" --llm-url "${FAST_URL:-http://127.0.0.1:8083}" --knowledge "$STATE/knowledge_candidates.jsonl" --once)
    [ -n "${WARM_URL:-}" ] && ARGS+=(--warm-url "$WARM_URL")
    [ "$DRY" = 1 ] && { say "[dry-run] python3 $DEST/idle_precompute.py ${ARGS[*]} --dry-run"; receipt CTX-idle-once true dry; exit 0; }
    if (cd "$DEST" && python3 -B idle_precompute.py "${ARGS[@]}" --sleep); then receipt CTX-idle-once true ok; else receipt CTX-idle-once false failed; exit 5; fi ;;
  status)
    say "DEST=$DEST STATE=$STATE"; [ -f "$STATE/state.json" ] && python3 -c "import json,sys;s=json.load(open(sys.argv[1]));print('segments',len(s['segments']),'cursor',s['cursor'],'epoch',s.get('epoch'))" "$STATE/state.json" || say "состояния ещё нет" ;;
  *) say "usage: ctx_ctl.sh install|selftest|idle-once|status [--dry-run]"; exit 1 ;;
esac
