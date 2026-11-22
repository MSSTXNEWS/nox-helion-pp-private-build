#!/usr/bin/env bash
# S1_07 ГОЛОС + ВЕБ (+ IMG, если есть в репо). Метка #S1. Если что-то не готово - этап пропускает это и пишет в квитанцию (status ok с skipped), но не ломает чат.
# Голос: WOW install_voice_s1.sh (Silero ru + Kokoro es + Piper; ставит в venv, тяжело -> фон), voice_server на :8098 (8095 занят recall!), presence :8096.
# Веб: nox-web-extras.js (фикс «ok:false» при правке факта, чтение после записи) и ассеты traits_panel/presence кладутся рядом в /root/nox/web с бэкапом; теги <script> в index.html - вручную (в квитанции).
# IMG: файлы wow7/img + тесты; веса (~55 ГБ) НЕ качаются без --with-img-weights (диск 122 ГБ!). Флаги: --dry-run --fg --status --rollback ; --no-voice --no-web --with-img-weights
SID=V7-07; STAGE_NO=7; TITLE="Голос, веб, IMG"; LONG=1
stage_plan() {
  echo "голос: sync wow,common; install_voice_s1.sh (без --start); voice_server NOX_VOICE_PORT=8098, presence :8096; проверка /health"
  echo "веб: sync web; найти /root/nox/web/**/nox-web-extras.js, бэкап, заменить; положить traits_panel.js/css, presence.js/css; перечислить нужные теги"
  echo "img: если набор img есть - sync + unittest; веса только с --with-img-weights (install_img_s1.sh --no-venv? нет: см. HANDOFF) и после проверки df"
}
RES_VOICE=skipped; RES_WEB=skipped; RES_IMG=skipped
do_voice() {
  v7_sync_set wow || return 1; v7_links; v7_test_mod wow || return 1
  NOX_CONTROL="$V7_CTL" NOX_RECEIPTS="$V7_RC" bash "$V7_W/wow/install_voice_s1.sh" > "$V7_RUN/voice_install.out" 2>&1 || { tail -5 "$V7_RUN/voice_install.out"; return 1; }
  python3 "$V7_TOOLS/gw_env.py" flags set NOX_VOICE_PORT=8098 >/dev/null
  python3 "$V7_TOOLS/gw_env.py" restart --match 'wow/voice_server\.py' --cwd "$V7_W/wow" --log "$V7_LOGS/voice_server.log" --health http://127.0.0.1:8098/health --timeout 90 --env-default "NOX_CONTROL=$V7_CTL" -- python3 "$V7_W/wow/voice_server.py" >/dev/null || return 1
  python3 "$V7_TOOLS/gw_env.py" restart --match 'wow/presence\.py' --cwd "$V7_W/wow" --log "$V7_LOGS/presence.log" --health http://127.0.0.1:8096/health --env-default "NOX_STATE=$V7_STATE" -- python3 "$V7_W/wow/presence.py" serve --port 8096 >/dev/null || return 1
}
do_web() {
  v7_sync_set web || return 1
  local ex dst; ex=$(find "$V7_HOME/web" -name nox-web-extras.js 2>/dev/null | head -1)
  [ -n "$ex" ] || { say "в $V7_HOME/web нет nox-web-extras.js - веб-ассеты не размещаю (деплой веба идёт веткой nox-web-dist)"; return 2; }
  dst=$(dirname "$ex"); local f; for f in "$V7_CTL/web/files/nox-web-extras.js" "$V7_W/traits/web/traits_panel.js" "$V7_W/traits/web/traits_panel.css" "$V7_W/wow/web/presence.js" "$V7_W/wow/web/presence.css"; do
    [ -f "$f" ] || continue; v7_bk_file "$dst/$(basename "$f")"; cp "$f" "$dst/$(basename "$f")"; done
  say "ассеты положены в $dst; ДОБАВЬ в index.html: traits_panel.css/.js, presence.css/.js (если ещё нет)"; WEB_DST="$dst"
  grep -q "nxw-merr" "$dst/nox-web-extras.js" || { say "после замены в extras нет фикса memErr"; return 1; }
  node -e "new Function(require('fs').readFileSync(process.argv[1],'utf8'))" "$dst/nox-web-extras.js" 2>/dev/null || { command -v node >/dev/null && { say "extras.js не парсится"; return 1; }; }
}
do_img() {
  v7_set_exists img || { say "набора img нет в манифесте (IMG ещё не влит)"; return 2; }
  v7_sync_set img || return 1; v7_links; v7_test_mod img || return 1
  if has_extra --with-img-weights; then
    local free; free=$(df -BG --output=avail "$V7_HOME" | tail -1 | tr -dc 0-9); [ "${free:-0}" -ge 70 ] || { say "для весов IMG нужно >=70 ГБ свободно, есть ${free} ГБ"; return 1; }
    NOX_HOME="$V7_HOME" NOX_CTL="$V7_CTL" SRC="$V7_W/img" bash "$V7_W/img/install_img_s1.sh" > "$V7_RUN/img_install.out" 2>&1 || { tail -5 "$V7_RUN/img_install.out"; return 1; }
  fi
}
stage_apply() {
  local r; v7_sync_set common || return 1
  has_extra --no-voice || { do_voice; r=$?; [ $r = 0 ] && RES_VOICE=ok || RES_VOICE="failed rc=$r"; }
  has_extra --no-web   || { do_web;   r=$?; [ $r = 0 ] && RES_WEB=ok || { [ $r = 2 ] && RES_WEB="skipped: нет web dir" || RES_WEB="failed"; }; }
  do_img; r=$?; [ $r = 0 ] && RES_IMG=ok || { [ $r = 2 ] && RES_IMG="skipped: нет в репо" || RES_IMG="failed"; }
  V7_RESULT="voice=$RES_VOICE;web=$RES_WEB;img=$RES_IMG"; say "$V7_RESULT"; v7_receipt running voice="$RES_VOICE" web="$RES_WEB" img="$RES_IMG" web_dir="${WEB_DST:-}"
  case "$RES_WEB$RES_VOICE" in *failed*) return 1;; esac; return 0
}
stage_health() { v7_health_regress && v7_http http://127.0.0.1:8082/v1/nox/stats 10; }
stage_rollback() { pkill -f 'wow/voice_server\.py' 2>/dev/null; pkill -f 'wow/presence\.py' 2>/dev/null; python3 "$V7_TOOLS/gw_env.py" flags unset NOX_VOICE_PORT >/dev/null 2>&1; return 0; }

V7_SELF="${BASH_SOURCE[0]}"; V7_SELF_DIR=$(cd "$(dirname "$V7_SELF")" && pwd)
if [ ! -f "$V7_SELF_DIR/lib_v7.sh" ]; then V7_SELF_DIR=/tmp/v7deploy; mkdir -p "$V7_SELF_DIR"; curl -fsSL "${V7_RAW:-https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main}/nox-control/wow7/deploy/lib_v7.sh?cb=$RANDOM" -o "$V7_SELF_DIR/lib_v7.sh" || { echo "не скачался lib_v7.sh" >&2; exit 9; }; fi
. "$V7_SELF_DIR/lib_v7.sh"

v7_main
