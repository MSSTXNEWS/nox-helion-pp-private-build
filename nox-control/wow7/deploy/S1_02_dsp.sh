#!/usr/bin/env bash
# S1_02 DSP ДИСПЕТЧЕР: сначала SHADOW (только наблюдает: nox_dispatcher --dry-run once x3), затем --promote (cron-сторож + запуск, усыновляет работающие сервисы). Метка #S1.
# По умолчанию: установка релиза в /root/nox/dsp БЕЗ cron/запуска + shadow-замер. Флаги: --dry-run --fg --status --rollback ; --promote (включить боевой режим) ; --auto-promote (после чистого shadow)
# Чистый shadow: реестр валиден, 3 тика без исключений, ни один сервис, который снаружи жив, диспетчер не считает DOWN.
# Откат: cron/onstart-блок dsp убраны, процессы dispatcher/watchdog остановлены, релиз -> previous или каталог dsp возвращён из бэкапа.
SID=V7-02; STAGE_NO=2; TITLE="DSP диспетчер (shadow -> promote)"; LONG=0
stage_plan() {
  echo "1. набор deploy,common,dsp из main; ссылки wow7; бэкап $V7_DSP, crontab, /root/onstart.sh"
  echo "2. install_dsp_s1.sh --no-cron (релиз в $V7_DSP/releases, тесты релиза внутри updater, без запуска); validate реестра"
  echo "3. SHADOW: 3 x 'nox_dispatcher --dry-run once' с паузой 20 с; сверка state сервисов с живыми портами -> $V7_RUN/dsp_shadow.json"
  echo "4. --promote / --auto-promote: install_dsp_s1.sh --start (cron каждую минуту + @reboot + блок в onstart; работающие сервисы усыновляются)"
}
DSPENV() { DSP_HOME="$V7_HOME" "$@"; }
shadow() {
  local i out="$V7_RUN/dsp_shadow.jsonl"; : > "$out"
  for i in 1 2 3; do DSPENV python3 "$V7_DSP/current/nox_dispatcher.py" --dry-run once >> "$out" 2>>"$V7_RUN/dsp_shadow.err" || say "тик $i: rc!=0"; [ $i -lt 3 ] && sleep "${V7_SHADOW_SLEEP:-20}"; done
  DSPENV python3 "$V7_DSP/current/nox_dispatcher.py" --dry-run status --json > "$V7_RUN/dsp_status.json" 2>>"$V7_RUN/dsp_shadow.err"
  python3 -I - "$V7_RUN/dsp_status.json" "$V7_RUN/dsp_shadow.json" "$V7_RUN/dsp_shadow.err" <<'PY'
import json, socket, sys
st, out, err = sys.argv[1:4]
try: s = json.load(open(st))
except Exception as e:
    json.dump({"clean": False, "why": "status не прочитан: %s" % e}, open(out, "w")); sys.exit(1)
def listening(p):
    try:
        socket.create_connection(("127.0.0.1", int(p)), 1).close(); return True
    except Exception: return False
rows, bad = [], []
for r in s.get("services", []):
    live = listening(r["port"]) if r.get("port") else None
    rows.append({"name": r["name"], "state": r["state"], "port": r["port"], "listening": live})
    if live and r["state"] not in ("UP", "LOADING", "STARTING"): bad.append("%s: слушает, а диспетчер видит %s" % (r["name"], r["state"]))
exc = [l for l in open(err, errors="replace") if "Traceback" in l]
res = {"clean": not bad and not exc, "mismatch": bad, "exceptions": len(exc), "services": rows, "stop": s.get("stop"), "quiet": s.get("quiet")}
json.dump(res, open(out, "w"), ensure_ascii=False, indent=1); print(json.dumps({k: res[k] for k in ("clean", "mismatch", "exceptions")}, ensure_ascii=False))
sys.exit(0 if res["clean"] else 1)
PY
}
stage_apply() {
  local s; for s in common dsp; do v7_sync_set "$s" || return 1; done
  v7_links
  v7_bk_file "$V7_DSP"; v7_bk_file "${DSP_ONSTART:-/root/onstart.sh}"; command -v crontab >/dev/null && crontab -l > "$BKD/crontab.before" 2>/dev/null || true
  if [ ! -d "$V7_DSP/current" ] || has_extra --reinstall; then
    DSP_ONSTART="$V7_RUN/onstart.shadow" DSP_HOME="$V7_HOME" SRC="$V7_W/dsp" bash "$V7_W/dsp/install_dsp_s1.sh" --no-cron || return 1   # shadow: блок автозапуска в настоящий onstart НЕ пишем
  else say "релиз DSP уже установлен: $(ls "$V7_DSP/releases" 2>/dev/null | tail -1)"; fi
  DSPENV python3 "$V7_DSP/current/nox_dispatcher.py" validate | tail -3 || return 1
  if has_extra --promote || has_extra --auto-promote; then
    if has_extra --auto-promote; then shadow || { say "shadow НЕ чистый - боевой режим не включаю"; return 1; }; fi
    DSP_HOME="$V7_HOME" SRC="$V7_W/dsp" bash "$V7_W/dsp/install_dsp_s1.sh" --start || return 1       # боевой: cron + onstart + запуск
    sleep 25; V7_PROMOTED=1
  else shadow || { say "shadow показал расхождения: $(cat "$V7_RUN/dsp_shadow.json" | tr -d '\n')"; return 1; }; fi
  v7_receipt running promoted="${V7_PROMOTED:-0}" shadow="$(tr -d '\n ' < "$V7_RUN/dsp_shadow.json")"
}
stage_health() {
  v7_health_regress || return 1
  if [ "${V7_PROMOTED:-0}" = 1 ]; then v7_dsp_live || { say "диспетчер не запущен после promote"; return 1; }; v7_dsp status | head -12; fi
  [ -f "$V7_RUN/dsp_shadow.json" ] && V7_RESULT="$(tr -d '\n ' < "$V7_RUN/dsp_shadow.json" | cut -c1-600)"
  return 0
}
stage_rollback() {
  command -v crontab >/dev/null && { crontab -l 2>/dev/null | grep -vE '# dsp-(watchdog|boot)' | crontab - 2>/dev/null || true; }
  pkill -f 'dsp/current/watchdog\.sh' 2>/dev/null; pkill -f 'nox_dispatcher\.py run' 2>/dev/null
  say "cron/процессы DSP убраны; сервисы чата НЕ остановлены (диспетчер только усыновлял)"; return 0
}

V7_SELF="${BASH_SOURCE[0]}"; V7_SELF_DIR=$(cd "$(dirname "$V7_SELF")" && pwd)
if [ ! -f "$V7_SELF_DIR/lib_v7.sh" ]; then V7_SELF_DIR=/tmp/v7deploy; mkdir -p "$V7_SELF_DIR"; curl -fsSL "${V7_RAW:-https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main}/nox-control/wow7/deploy/lib_v7.sh?cb=$RANDOM" -o "$V7_SELF_DIR/lib_v7.sh" || { echo "не скачался lib_v7.sh" >&2; exit 9; }; fi
. "$V7_SELF_DIR/lib_v7.sh"

v7_main
