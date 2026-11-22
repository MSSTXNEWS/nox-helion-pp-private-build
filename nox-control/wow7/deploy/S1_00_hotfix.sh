#!/usr/bin/env bash
# S1_00 СРОЧНЫЙ ФИКС ЧАТА (HOTFIX_NOW.md): Prime-режим вместо пересказа телеметрии, служебное не в тексте. Метка #S1.
# Что: набор common+prime+hotfix (шлюз с врезкой Prime/CORE-прокси, gateway_prime/nox_prime/soul_prime_v3, patch_chat.py с фильтром служебного, conscience.py),
#      флаги NOX_PRIME=1 (NOX_CORE не трогаем), перезапуск шлюза и веба, проверка: «привет» x3 -> живые разные ответы без телеметрии/«Жду твой ввод».
# Откат: файлы из бэкапа, NOX_PRIME убран, перезапуск. Квитанция /root/nox/receipts/V7-00.json. Флаги: --dry-run --fg --status --rollback
SID=V7-00; STAGE_NO=0; TITLE="Срочный фикс чата (Prime, фильтр служебного)"; LONG=0
BADRE='RTX|GPU|vCPU|ГБ|ток/с|tok/s|Жду твой ввод|Что хочешь|Пустота в очереди|задача t[0-9]|Глубокий ответ|готовлю в фоне'
stage_plan() {
  echo "1. набор deploy,common,prime,hotfix из main (sha256 по MANIFEST), бэкап заменяемых файлов"
  echo "2. ссылки wow7: UPPER->lower, /root/nox/src/wow7"
  echo "3. флаги NOX_PRIME=1 NOX_WOW7=$V7_W -> $V7_STATE/v7_flags.json (+local.json DSP, если диспетчер жив)"
  echo "4. перезапуск gateway и web; поиск строк служебного текста на сервере (отчёт, без правки чужого кода)"
  echo "5. проба «привет» x3 (до и после): без маркеров '$BADRE', >=2 разных ответа; порты, что были, живы"
}
hi_probe() {  # $1 файл-выход; 3 пробы
  : > "$1"; local i; for i in 1 2 3; do v7_chat_probe auto 60 120 "привет" >> "$1" 2>/dev/null || true; sleep 1; done
}
hi_check() {  # rc 0 если хорошо
  python3 -I - "$1" "$BADRE" <<'PY'
import json, re, sys
rows = [json.loads(l) for l in open(sys.argv[1]) if l.strip().startswith("{")]
bad = re.compile(sys.argv[2])
ok = [r for r in rows if r.get("ok")]
texts = [r["text"] for r in ok]
clean = [t for t in texts if not bad.search(t)]
res = {"answers": len(ok), "clean": len(clean), "distinct": len(set(texts)), "samples": texts[:3]}
print(json.dumps(res, ensure_ascii=False))
sys.exit(0 if len(ok) == 3 and len(clean) == 3 and len(set(texts)) >= 2 else 1)
PY
}
stage_apply() {
  local s before="$V7_RUN/$SID.hi_before" f
  v7_http http://127.0.0.1:8082/v1/nox/stats && { hi_probe "$before"; V7_BEFORE=$(hi_check "$before" 2>&1 | tail -1); say "ДО: $V7_BEFORE"; }
  for s in common prime hotfix; do v7_sync_set "$s" || return 1; done
  v7_links; v7_bk_file "$V7_STATE/v7_flags.json"
  v7_flag set NOX_PRIME=1 "NOX_WOW7=$V7_W"
  v7_restart gateway || return 1
  pgrep -f 'web_server\.py' >/dev/null && v7_restart web
  local hits; hits=$(grep -rnE 'Глубокий ответ GLM-5.3 готовлю в фоне|Быстрый слой ответил пусто' "$V7_HOME/web_server.py" "$V7_CTL/s1web" "$V7_CTL/web" "$V7_HOME/web" 2>/dev/null | cut -c1-160 | head -5 | tr '\n' '|')
  v7_receipt running service_text_lines="${hits:-нет}" before="${V7_BEFORE:-нет шлюза}"; say "служебные строки в серверных файлах: ${hits:-нет}"
  return 0
}
stage_health() {
  v7_health_regress || return 1
  v7_http http://127.0.0.1:8082/v1/nox/stats 10 || { say "шлюз не отвечает"; return 1; }
  local after="$V7_RUN/$SID.hi_after" r; hi_probe "$after"; r=$(hi_check "$after" 2>&1 | tail -1); say "ПОСЛЕ: $r"; V7_RESULT="$r"
  hi_check "$after" >/dev/null 2>&1
}
stage_rollback() { v7_flag unset NOX_PRIME NOX_WOW7; v7_restart gateway; pgrep -f 'web_server\.py' >/dev/null && v7_restart web; return 0; }

V7_SELF="${BASH_SOURCE[0]}"; V7_SELF_DIR=$(cd "$(dirname "$V7_SELF")" && pwd)
if [ ! -f "$V7_SELF_DIR/lib_v7.sh" ]; then V7_SELF_DIR=/tmp/v7deploy; mkdir -p "$V7_SELF_DIR"; curl -fsSL "${V7_RAW:-https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main}/nox-control/wow7/deploy/lib_v7.sh?cb=$RANDOM" -o "$V7_SELF_DIR/lib_v7.sh" || { echo "не скачался lib_v7.sh" >&2; exit 9; }; fi
. "$V7_SELF_DIR/lib_v7.sh"

v7_main
