#!/usr/bin/env bash
# DSP-02 install_dsp_s1: установка диспетчера NOX на S1 БЕЗ systemd: релиз -> current, cron (watchdog раз в минуту + @reboot), блок в /root/onstart.sh,
# запуск. Метка #S1. Идемпотентен. Ничего не останавливает и не перезапускает у работающих сервисов (диспетчер их усыновляет).
# Использование: install_dsp_s1.sh [--dry-run] [--start] [--systemd] [--no-cron] [--from-github] [--skip-tests]
# Env: DSP_HOME (/root/nox) DSP_ONSTART (/root/onstart.sh) SRC (каталог с файлами; по умолчанию рядом со скриптом)
set -euo pipefail
DRY=0; START=0; SYSTEMD=0; CRON=1; GH=0
for a in "$@"; do case "$a" in --dry-run) DRY=1;; --start) START=1;; --systemd) SYSTEMD=1;; --no-cron) CRON=0;; --from-github) GH=1;; --skip-tests) :;;
  *) echo "неизвестный флаг $a" >&2; exit 2;; esac; done
H="${DSP_HOME:-/root/nox}"; I="$H/dsp"; ONSTART="${DSP_ONSTART:-/root/onstart.sh}"; RC_DIR="$H/receipts"
SRC="${SRC:-$(cd "$(dirname "$0")" && pwd)}"
RAW="https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/wow7/dsp"
FILES="nox_dispatcher.py playbooks.py updater.py wake.py watchdog.sh services.json test_dsp.py fake_service.py nox-dsp.service dsp_ping.py"
run() { if [ "$DRY" = 1 ]; then echo "[dry-run] $*"; else eval "$@"; fi; }
note() { echo "== $*"; }

if [ "$GH" = 1 ]; then
  note "скачиваю файлы из main ($RAW)"
  T=$(mktemp -d); for f in $FILES; do
    if [ "$DRY" = 1 ]; then echo "[dry-run] curl -fsSL $RAW/$f -o $T/$f"; else curl -fsSL "$RAW/$f" -o "$T/$f" || { echo "не скачался $f" >&2; exit 1; }; fi
  done; [ "$DRY" = 1 ] && T="$SRC"; SRC="$T"
fi
for f in nox_dispatcher.py playbooks.py updater.py wake.py watchdog.sh services.json test_dsp.py fake_service.py; do
  [ -f "$SRC/$f" ] || { echo "нет файла $SRC/$f" >&2; exit 1; }; done
command -v python3 >/dev/null || { echo "нужен python3" >&2; exit 1; }
bash -n "$SRC/watchdog.sh" || { echo "watchdog.sh: синтаксис" >&2; exit 1; }
for f in nox_dispatcher.py playbooks.py updater.py wake.py; do python3 -c "import ast,sys;ast.parse(open(sys.argv[1]).read())" "$SRC/$f" || { echo "$f: синтаксис" >&2; exit 1; }; done

note "1. релиз в $I/releases (тесты релиза запускаются внутри updater.py install; красные = отказ)"
run "mkdir -p '$I' '$H/logs' '$H/run' '$H/state' '$RC_DIR'"
if [ "$DRY" = 1 ]; then echo "[dry-run] DSP_HOME=$H python3 $SRC/updater.py install $SRC"; VER=dry
else VER=$(DSP_HOME="$H" python3 "$SRC/updater.py" install "$SRC" | tail -1) || { echo "установка релиза не прошла (тесты/проверки)" >&2; exit 1; }; fi
[ -f "$I/local.json" ] || run "echo '{}' > '$I/local.json'"

note "2. проверка реестра"
if [ "$DRY" = 1 ]; then echo "[dry-run] DSP_HOME=$H python3 $I/current/nox_dispatcher.py validate"; else DSP_HOME="$H" python3 "$I/current/nox_dispatcher.py" validate; fi

note "3. cron (сторож раз в минуту) и onstart"
CRON_STATE=skipped
if [ "$CRON" = 1 ]; then
  if command -v crontab >/dev/null; then
    LINE1="* * * * * DSP_HOME=$H bash $I/current/watchdog.sh --once >> $H/logs/dsp_watchdog.log 2>&1 # dsp-watchdog"
    LINE2="@reboot DSP_HOME=$H bash $I/current/watchdog.sh --boot >> $H/logs/dsp_watchdog.log 2>&1 # dsp-boot"
    if [ "$DRY" = 1 ]; then echo "[dry-run] crontab += $LINE1"; echo "[dry-run] crontab += $LINE2"
    else (crontab -l 2>/dev/null | grep -vE "# dsp-(watchdog|boot)"; echo "$LINE1"; echo "$LINE2") | crontab -; fi
    pgrep -x cron >/dev/null 2>&1 || pgrep -x crond >/dev/null 2>&1 || { run "(cron || service cron start) >/dev/null 2>&1 || true"; }
    CRON_STATE=installed
  else CRON_STATE=no_crontab_binary; echo "crontab нет: сторож будет работать как 'watchdog.sh --loop' (его запускает onstart и сам диспетчер)"; fi
fi
BLOCK="# >>> dsp >>>
DSP_HOME=$H nohup setsid bash $I/current/watchdog.sh --loop >> $H/logs/dsp_watchdog.log 2>&1 < /dev/null &
# <<< dsp <<<"
if [ "$DRY" = 1 ]; then echo "[dry-run] $ONSTART: блок dsp добавлен/обновлён (остальное содержимое сохраняется)"
else
  [ -f "$ONSTART" ] || printf '#!/bin/bash\n' > "$ONSTART"
  python3 - "$ONSTART" "$BLOCK" <<'PY'
import re, sys
p, block = sys.argv[1], sys.argv[2]
s = open(p).read()
s = re.sub(r"# >>> dsp >>>.*?# <<< dsp <<<\n?", "", s, flags=re.S)
if not s.endswith("\n"): s += "\n"
open(p, "w").write(s + block + "\n")
PY
  chmod +x "$ONSTART"
fi

SYSD=skipped
if [ "$SYSTEMD" = 1 ]; then
  if [ -d /run/systemd/system ]; then run "install -m 0644 '$SRC/nox-dsp.service' /etc/systemd/system/nox-dsp.service && systemctl daemon-reload && systemctl enable nox-dsp.service"; SYSD=enabled
  else SYSD=no_systemd; echo "systemd в контейнере нет - используется cron/onstart"; fi
fi

STARTED=no
if [ "$START" = 1 ]; then
  note "4. запуск (сторож поднимет диспетчер; работающие сервисы будут усыновлены)"
  run "DSP_HOME='$H' bash '$I/current/watchdog.sh' --once"
  STARTED=yes
fi

RC="$RC_DIR/DSP-02.json"
BODY=$(printf '{"id":"DSP-02","ts":"%s","dry_run":%s,"version":"%s","cron":"%s","systemd":"%s","started":"%s","home":"%s"}' "$(date -u +%FT%TZ)" "$([ $DRY = 1 ] && echo true || echo false)" "$VER" "$CRON_STATE" "$SYSD" "$STARTED" "$H")
if [ "$DRY" = 1 ]; then echo "[dry-run] квитанция $RC: $BODY"; else echo "$BODY" > "$RC"; echo "ok: $RC"; fi
