#!/bin/bash
# S1: память NOX (S03): сверка бэкапа старого NOX -> распаковка -> импорт (сначала dry_run, потом реально) -> cron бэкапа каждый час.
# Бэкап скопирован на S1 скриптом c97/s1_pull.sh в /root/nox/backup_s2 (memory.tar.zstd, state.tar.zstd, SHA256SUMS).
# Идемпотентен: повторный запуск не плодит дубликаты (импорт и cron). Ничего не удаляет. Запускать на S1 вручную или из boot_s1.sh.
# Переменные: NOX_MEMORY_DB (по умолчанию /root/nox/memory/s03.db), NOX_BACKUP_SRC (/root/nox/backup_s2), NOX_MEMORY_BACKUP_DIR, NOX_MEMORY_BACKUP_KEEP.
set -u
N=${NOX_HOME:-/root/nox}; C=${NOX_CONTROL:-$N/repo/nox-control}
DB=${NOX_MEMORY_DB:-$N/memory/s03.db}; SRC=${NOX_BACKUP_SRC:-$N/backup_s2}; UNP=$SRC/unpacked
BK=${NOX_MEMORY_BACKUP_DIR:-$N/memory/backups}; KEEP=${NOX_MEMORY_BACKUP_KEEP:-24}; LG=$N/logs
mkdir -p "$(dirname "$DB")" "$BK" "$LG"
log(){ echo "[$(date +%H:%M:%S)] memory_boot: $*" | tee -a "$LG/boot.log"; }
PY(){ (cd "$C" && python3 "$@"); }
[ -d "$C/qs6" ] || { log "нет $C/qs6 (репозиторий не обновлён?)"; exit 2; }
# 1. сверка sha256 бэкапа (по SHA256SUMS; без неё распаковывать нельзя)
if [ ! -f "$SRC/SHA256SUMS" ]; then log "нет $SRC/SHA256SUMS: бэкап не скопирован (c97/s1_pull.sh), импорт пропущен"; IMPORT=0
elif ! (cd "$SRC" && sha256sum -c --ignore-missing SHA256SUMS >"$LG/memory_sha.log" 2>&1); then log "sha256 бэкапа НЕ сошёлся, см. $LG/memory_sha.log: импорт отменён"; IMPORT=0
else log "sha256 бэкапа сошёлся"; IMPORT=1; fi
# 2. распаковка memory и state (только то, что нужно памяти и личности)
if [ "$IMPORT" = 1 ] && [ ! -f "$UNP/.done" ]; then
  mkdir -p "$UNP"; ok=1
  for a in memory state; do
    f=""; for x in zstd gzip gz; do [ -f "$SRC/$a.tar.$x" ] && { f=$SRC/$a.tar.$x; break; }; done   # c95/backup_s2.sh: .tar.zstd или .tar.gzip
    [ -n "$f" ] || { log "нет архива $a: пропуск"; continue; }
    mkdir -p "$UNP/$a"
    case "$f" in *.zstd) zstd -dc "$f" | tar -x -C "$UNP/$a" --no-same-owner --no-same-permissions;; *) tar -xzf "$f" -C "$UNP/$a" --no-same-owner --no-same-permissions;; esac || { log "не распаковался $f (zstd установлен?)"; ok=0; }
  done
  [ -f "$SRC/KNOWLEDGE_TRANSFER.md" ] && cp "$SRC/KNOWLEDGE_TRANSFER.md" "$UNP/"
  [ "$ok" = 1 ] && touch "$UNP/.done"
fi
# 3. импорт: dry_run, потом реально
if [ "$IMPORT" = 1 ] && [ -d "$UNP" ]; then
  PY -m qs6.import_cli --db "$DB" --root "$UNP" --dry-run > "$LG/memory_import_dry.log" 2>&1; rc=$?
  head -3 "$LG/memory_import_dry.log" | tee -a "$LG/boot.log"
  if [ $rc -eq 0 ]; then
    PY -m qs6.import_cli --db "$DB" --root "$UNP" > "$LG/memory_import.log" 2>&1 && log "импорт выполнен: $(head -1 $LG/memory_import.log)" || log "импорт упал, см. $LG/memory_import.log"
  else log "dry_run вернул код $rc (3 = нечего принимать): реальный импорт НЕ запускаю, см. $LG/memory_import_dry.log"; fi
fi
# 4. cron: бэкап БД каждый час (@hourly), идемпотентно
if [ -f "$DB" ]; then
  LINE="@hourly cd $C && NOX_MEMORY_DB=$DB python3 qs6/backup_memory.py backup --db $DB --dir $BK --keep $KEEP >> $BK/backup.log 2>&1 # nox-memory-backup"
  (crontab -l 2>/dev/null | grep -v "# nox-memory-backup"; echo "$LINE") | crontab - 2>/dev/null && log "cron @hourly бэкап памяти поставлен" || log "crontab недоступен: поставьте вручную: $LINE"
  PY qs6/backup_memory.py backup --db "$DB" --dir "$BK" --keep "$KEEP" >> "$BK/backup.log" 2>&1 && log "первая копия памяти сделана" || log "первая копия не удалась, см. $BK/backup.log"
else log "БД $DB ещё нет (импорт не выполнен): cron бэкапа не ставлю; шлюз работает без памяти (NOX_MEMORY_CREATE=1 создаёт пустую)"; fi
