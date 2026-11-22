#!/usr/bin/env bash
# S1_05 PRIME/душа v3 + MEM-патчи + CTX. Метка #S1. ЖЁСТКИЙ ВОРОТА: свежий бэкап S03 (MEM-13) ДО замены memory_layer.py/recall_server.py.
# Что: sync mem,memlayer(патчи MEM/PER к qs6/memory_layer.py и recall_server.py),per,ctx,prime,hotfix; бэкап S03 + почасовой cron; unittest mem/ctx/per; перезапуск recall и шлюза;
#      прогрев KV души (soul_prime_v3) через soul_kv_warm; проверка: «привет», вопрос о памяти, S03 читается. Откат: файлы, cron, перезапуск recall/шлюза.
# Флаги: --dry-run --fg --status --rollback
SID=V7-05; STAGE_NO=5; TITLE="Душа v3 (Prime) + память MEM + контекст CTX"; LONG=0
stage_plan() {
  echo "1. бэкап S03: backup_s03.sh (sqlite .backup) -> MEM-13.json; без свежего бэкапа (<2 ч) дальше не иду"
  echo "2. sync prime,hotfix,mem,memlayer,per,ctx,common; ссылки; unittest mem, ctx, per"
  echo "3. cron $V7_HOME: почасовой backup_s03.sh (/etc/cron.d/nox-v7-backup)"
  echo "4. NOX_PRIME=1 (уже с S1_00), перезапуск recall (:8095) и шлюза; soul_kv_warm.sh по soul_prime_v3.txt (если GLM жив)"
  echo "5. здоровье: recall /health, чат «привет», вопрос о памяти; S03 читается; порты живы"
}
stage_apply() {
  local db; db=$(v7_s03_db); [ -f "$db" ] || { say "нет базы S03: $db"; return 1; }
  v7_sync_set common || return 1; v7_sync_set mem || return 1
  S03_DB="$db" BACKUP_DIR="$V7_HOME/memory/backups" RECEIPTS="$V7_RC" bash "$V7_W/mem/backup_s03.sh" || { say "бэкап S03 не сделан - стоп"; return 1; }
  S03_DB="$db" BACKUP_DIR="$V7_HOME/memory/backups" RECEIPTS="$V7_RC" bash "$V7_W/mem/backup_s03.sh" --require-fresh 7200 || return 1
  local s; for s in prime hotfix memlayer per ctx; do v7_sync_set "$s" || return 1; done; v7_links
  for s in mem per ctx; do v7_test_mod "$s" || return 1; done
  v7_bk_file /etc/cron.d/nox-v7-backup; v7_bk_file "$V7_STATE/v7_flags.json"
  [ -d /etc/cron.d ] && printf '7 * * * * root S03_DB=%s BACKUP_DIR=%s RECEIPTS=%s bash %s/mem/backup_s03.sh >>%s/mem_backup.log 2>&1\n' "$db" "$V7_HOME/memory/backups" "$V7_RC" "$V7_W" "$V7_LOGS" > /etc/cron.d/nox-v7-backup
  v7_flag set NOX_PRIME=1 "NOX_WOW7=$V7_W"
  pgrep -f 'qs6\.recall_server' >/dev/null && { v7_restart recall || return 1; }
  v7_restart gateway || return 1
  if v7_http http://127.0.0.1:8081/health 5; then
    local soul="$V7_CTL/glm53/soul_prime_v3.txt"; [ -f "$soul" ] || soul="$V7_W/prime/soul_prime_v3.txt"
    bash "$V7_W/spd/soul_kv_warm.sh" --soul "$soul" auto > "$V7_RUN/soul_prime_kv.out" 2>&1 && say "KV души v3: $(tail -1 "$V7_RUN/soul_prime_kv.out" | cut -c1-160)" || say "soul_kv_warm не удался (не критично, см. $V7_RUN/soul_prime_kv.out)"
  fi
  return 0
}
stage_health() {
  v7_health_regress || return 1
  v7_http http://127.0.0.1:8082/v1/nox/stats 10 || return 1
  pgrep -f 'qs6\.recall_server' >/dev/null && { v7_http http://127.0.0.1:8095/health 5 || { say "recall не здоров"; return 1; }; }
  v7_chat_probe fast 40 120 "привет" | tee "$V7_RUN/p5_hi.json" | cut -c1-200; grep -q '"ok": true' "$V7_RUN/p5_hi.json" || return 1
  v7_chat_probe fast 60 120 "Что ты помнишь обо мне? Если не знаешь - скажи честно." | tee "$V7_RUN/p5_mem.json" | cut -c1-200; grep -q '"ok": true' "$V7_RUN/p5_mem.json" || return 1
  python3 -I - "$(v7_s03_db)" <<'PY' || return 1
import sqlite3, sys
c = sqlite3.connect("file:%s?mode=ro" % sys.argv[1], uri=True); n = c.execute("select count(*) from sqlite_master").fetchone()[0]; print("S03 читается, объектов схемы:", n)
PY
  V7_RESULT="prime=1 mem=patched ctx=ok backup=fresh"
}
stage_rollback() { rm -f /etc/cron.d/nox-v7-backup; v7_flag unset NOX_PRIME; pgrep -f 'qs6\.recall_server' >/dev/null && v7_restart recall; v7_restart gateway; return 0; }

V7_SELF="${BASH_SOURCE[0]}"; V7_SELF_DIR=$(cd "$(dirname "$V7_SELF")" && pwd)
if [ ! -f "$V7_SELF_DIR/lib_v7.sh" ]; then V7_SELF_DIR=/tmp/v7deploy; mkdir -p "$V7_SELF_DIR"; curl -fsSL "${V7_RAW:-https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main}/nox-control/wow7/deploy/lib_v7.sh?cb=$RANDOM" -o "$V7_SELF_DIR/lib_v7.sh" || { echo "не скачался lib_v7.sh" >&2; exit 9; }; fi
. "$V7_SELF_DIR/lib_v7.sh"

v7_main
