#!/usr/bin/env bash
# lib_v7.sh - общая библиотека этапов S1_00..S1_08 (source). Метка #S1.
# Скрипт этапа до source задаёт: SID (V7-0N), STAGE_NO, TITLE, LONG (1 = по умолчанию уходит в фон nohup setsid), и функции
#   stage_plan (что сделаю, печатает), stage_apply (делает; rc!=0 = провал), stage_health (rc!=0 = провал), stage_rollback (доп. откат сверх файлов).
# Общие флаги: --dry-run  --fg (не уходить в фон)  --status  --rollback  --force  --allow-daytime  --help ; прочие -> массив V7_EXTRA.
# Окружение (для песочницы/тестов все пути переопределяются): V7_HOME(/root/nox) V7_RAW V7_REPO V7_CTL V7_STATE V7_RECEIPTS V7_LOGS V7_BK.
V7_HOME=${V7_HOME:-/root/nox}
V7_RAW=${V7_RAW:-https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main}
V7_REPO=${V7_REPO:-$V7_HOME/repo}
if [ -z "${V7_CTL:-}" ]; then for _c in "$V7_REPO/nox-control" "$V7_HOME/src/nox-control"; do [ -d "$_c" ] && { V7_CTL=$_c; break; }; done; V7_CTL=${V7_CTL:-$V7_REPO/nox-control}; fi
V7_STATE=${V7_STATE:-$V7_HOME/state}; V7_RC=${V7_RECEIPTS:-$V7_HOME/receipts}; V7_LOGS=${V7_LOGS:-$V7_HOME/logs}; V7_BK=${V7_BK:-$V7_HOME/backups/v7}
V7_W=$V7_CTL/wow7; V7_TOOLS=$V7_W/deploy; V7_DSP=${V7_DSP:-$V7_HOME/dsp}; V7_RUN=$V7_STATE/v7
V7_PORTS=${V7_PORTS:-"8081 8082 8083 8084 8090 8091 8095"}
V7_SELF=${V7_SELF:-$0}; V7_LIB=${BASH_SOURCE[0]}
export PYTHONDONTWRITEBYTECODE=1 V7_STATE
DRY=0; FG=0; STATUS=0; ROLLBACK=0; FORCE=0; ALLOW_DAY=0; V7_EXTRA=(); V7_ARGV=("$@")
MAN=""; BKD=""

say()  { echo "[$SID $(date +%T)] $*"; }
die()  { say "ОШИБКА: $1" >&2; [ "$DRY" = 0 ] && [ "${2:-1}" != 4 ] && v7_receipt failed reason="$1" rc="${2:-1}" >/dev/null 2>&1; exit "${2:-1}"; }
x()    { if [ "$DRY" = 1 ]; then echo "[dry-run] $*"; return 0; fi; "$@"; }
rawurl() { case "$V7_RAW" in http*) echo "$V7_RAW/$1?cb=$RANDOM$RANDOM";; *) echo "$V7_RAW/$1";; esac; }
py()   { python3 -I "$@"; }
pyt()  { python3 "$@"; }                      # для инструментов рядом с пакетами (нужен sys.path скрипта)

v7_parse() {
  while [ $# -gt 0 ]; do case "$1" in
    "") ;; --dry-run) DRY=1;; --fg) FG=1;; --status) STATUS=1;; --rollback) ROLLBACK=1;; --force) FORCE=1;; --allow-daytime) ALLOW_DAY=1;;
    -h|--help) sed -n '2,12p' "$V7_SELF" 2>/dev/null; echo "флаги: --dry-run --fg --status --rollback --force --allow-daytime"; exit 0;;
    *) V7_EXTRA+=("$1");; esac; shift; done
}
has_extra() { local e; for e in "${V7_EXTRA[@]:-}"; do [ "$e" = "$1" ] && return 0; done; return 1; }
extra_val() { local i; for ((i=0;i<${#V7_EXTRA[@]};i++)); do [ "${V7_EXTRA[$i]}" = "$1" ] && { echo "${V7_EXTRA[$((i+1))]:-}"; return 0; }; done; return 1; }

# ---------------------------------------------------------------- квитанция
# v7_receipt STATUS [k=v ...]  (v - JSON, если начинается с { [ или число/true/false/null, иначе строка). STATUS: dry|running|ok|failed|rolled_back
v7_receipt() {
  local st="$1"; shift
  if [ "$DRY" = 1 ]; then echo "[dry-run] квитанция $V7_RC/$SID.json status=$st $*"; return 0; fi
  mkdir -p "$V7_RC"
  python3 -I - "$V7_RC/$SID.json" "$SID" "$STAGE_NO" "$TITLE" "$st" "$V7_LOGS/$SID.log" "$@" <<'PY'
import json, os, sys, time
p, sid, no, title, st, log = sys.argv[1:7]
d = {"id": sid, "stage": int(no), "title": title, "status": st, "ok": st == "ok", "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
     "host": os.uname().nodename, "log": log}
try:
    old = json.load(open(p))
    if isinstance(old, dict):
        for k, v in old.items():
            if not (st == "ok" and k in ("reason", "error", "result_failed")):
                d.setdefault(k, v)
except Exception:
    pass
for kv in sys.argv[7:]:
    k, _, v = kv.partition("=")
    try:
        d[k] = json.loads(v) if v[:1] in "{[" or v in ("true", "false", "null") or v.lstrip("-").replace(".", "", 1).isdigit() else v
    except ValueError:
        d[k] = v
d["status"], d["ok"] = st, st == "ok"
tmp = p + ".tmp"
json.dump(d, open(tmp, "w"), ensure_ascii=False, indent=1)
os.replace(tmp, p)
PY
}

# ---------------------------------------------------------------- бэкап/откат файлов
v7_bk_begin() {
  BKD="$V7_BK/$SID/$(date +%Y%m%dT%H%M%S)"
  [ "$DRY" = 1 ] && { echo "[dry-run] бэкап-каталог $BKD"; return 0; }
  mkdir -p "$BKD/files" && : > "$BKD/absent.list" && echo "$BKD" > "$V7_BK/$SID/latest"
}
v7_bk_file() {      # путь файла/ссылки ДО изменения
  local f="$1"
  [ "$DRY" = 1 ] && return 0
  [ -n "$BKD" ] || v7_bk_begin
  if [ -e "$f" ] || [ -L "$f" ]; then
    if [ ! -e "$BKD/files$f" ] && [ ! -L "$BKD/files$f" ]; then mkdir -p "$BKD/files$(dirname "$f")" && cp -a "$f" "$BKD/files$f"; fi
  else grep -qxF "$f" "$BKD/absent.list" || echo "$f" >> "$BKD/absent.list"; fi
}
v7_bk_restore() {   # все файлы последнего бэкапа этапа (или только перечисленные в файле-списке $1)
  local d only="${1:-}"; d=$(cat "$V7_BK/$SID/latest" 2>/dev/null)
  [ -d "$d" ] || { say "бэкапа нет - откат файлов нечем делать"; return 1; }
  local p f
  while IFS= read -r p; do
    f="${p#.}"; [ -n "$only" ] && ! grep -qxF "$f" "$only" && continue
    rm -rf -- "$f"; mkdir -p "$(dirname "$f")"; cp -a "$d/files/$p" "$f"
  done < <(cd "$d/files" 2>/dev/null && find . \( -type f -o -type l \) )
  while IFS= read -r f; do [ -n "$f" ] || continue; [ -n "$only" ] && ! grep -qxF "$f" "$only" && continue; rm -rf -- "$f"; done < "$d/absent.list"
  say "файлы восстановлены из $d"
}

# ---------------------------------------------------------------- доставка файлов из репо (git pull + sha256 по MANIFEST, добор через raw)
v7_manifest() {
  [ -n "$MAN" ] && [ -s "$MAN" ] && return 0
  MAN=$(mktemp); local i
  for i in 1 2 3; do curl -fsSL -m 60 "$(rawurl nox-control/wow7/deploy/MANIFEST.tsv)" -o "$MAN" && [ -s "$MAN" ] && return 0; sleep 5; done
  rm -f "$MAN"; MAN=""; return 1
}
v7_set_exists() { v7_manifest && awk -F'\t' -v s="$1" '$1==s{f=1} END{exit !f}' "$MAN"; }
# v7_sync_set NAME : скачать/сверить все файлы набора; изменённые - в бэкап; список изменённых: $V7_RUN/$SID.NAME.changed
v7_sync_set() {
  local set="$1" sha path dest got n=0 bad=0 ch="$V7_RUN/$SID.$set.changed"
  v7_manifest || { say "не скачался MANIFEST.tsv из $V7_RAW (репо не влито в main?)"; return 2; }
  v7_set_exists "$set" || { say "набор '$set' пуст/нет в манифесте"; return 3; }
  if [ "$DRY" = 1 ]; then echo "[dry-run] sync набор $set: $(awk -F'\t' -v s="$set" '$1==s' "$MAN" | wc -l) файлов -> $V7_CTL"; return 0; fi
  mkdir -p "$V7_RUN"; : > "$ch"
  if [ -d "$V7_REPO/.git" ] && [ "${V7_NO_PULL:-0}" != 1 ]; then git -C "$V7_REPO" pull -q --ff-only >/dev/null 2>&1 || true; fi
  while IFS=$'\t' read -r _ sha path; do
    dest="$V7_CTL/${path#nox-control/}"
    if [ -f "$dest" ] && [ "$(sha256sum "$dest" | cut -c1-64)" = "$sha" ]; then continue; fi
    got=""; local t
    for t in 1 2 3; do
      curl -fsSL -m 120 "$(rawurl "$path")" -o "$MAN.dl" 2>/dev/null && [ "$(sha256sum "$MAN.dl" | cut -c1-64)" = "$sha" ] && { got=1; break; }; sleep 5
    done
    [ -n "$got" ] || { say "sha256 не сошёлся: $path (кэш raw ~5 мин? повтори)"; bad=$((bad+1)); continue; }
    v7_bk_file "$dest"; mkdir -p "$(dirname "$dest")"; cp "$MAN.dl" "$dest.v7new" && { case "$path" in *.sh) chmod +x "$dest.v7new";; esac; mv -f "$dest.v7new" "$dest"; }
    echo "$dest" >> "$ch"; n=$((n+1))
  done < <(awk -F'\t' -v s="$set" '$1==s' "$MAN")
  rm -f "$MAN.dl"; say "набор $set: обновлено файлов $n, ошибок $bad"
  [ "$bad" = 0 ]
}
# имена модулей: wow7/<lower> -> wow7/<UPPER> (модули ищут друг друга по верхнему регистру) и /root/nox/src/wow7
v7_links() {
  [ "$DRY" = 1 ] && { echo "[dry-run] ссылки WOW7: UPPER->lower в $V7_W, $V7_HOME/src/wow7 -> $V7_W"; return 0; }
  local d n U
  for d in "$V7_W"/*/; do n=$(basename "$d"); [ "$n" = deploy ] && continue; U=$(echo "$n" | tr a-z A-Z); [ "$n" != "$U" ] && [ ! -e "$V7_W/$U" ] && ln -s "$n" "$V7_W/$U"; done
  mkdir -p "$V7_HOME/src"; v7_place_dir "$V7_W" "$V7_HOME/src/wow7"
}
v7_place_dir() {    # $1 источник, $2 назначение: нет -> симлинк; симлинк -> перенацелить; реальный каталог -> скопировать файлы поверх (с бэкапом)
  local s="$1" d="$2" f
  [ "$DRY" = 1 ] && { echo "[dry-run] place $s -> $d"; return 0; }
  if [ -L "$d" ] || [ ! -e "$d" ]; then v7_bk_file "$d"; ln -sfn "$s" "$d"
  else (cd "$s" && find . -type f ! -name '*.pyc' | while read -r f; do v7_bk_file "$d/${f#./}"; mkdir -p "$(dirname "$d/$f")"; cp "$f" "$d/$f"; done); fi
}

# ---------------------------------------------------------------- проверки и здоровье
v7_quiet() { python3 -I -c 'import datetime as d;h=(d.datetime.utcnow()+d.timedelta(hours=3)).hour;raise SystemExit(0 if h>=23 or h<8 else 1)'; }
v7_stop_active() { [ -e /run/nox/STOP ] || [ -e "$V7_HOME/STOP" ]; }
v7_sweep_active() { pgrep -f 'glm_sweep|ik_llama|bench_glm\.py|gpu_tier/run\.sh|llama-bench|llama-sweep' >/dev/null 2>&1; }
v7_http() { curl -fsS -m "${2:-4}" -o /dev/null "$1" 2>/dev/null; }
v7_up_ports() { local p o=""; for p in $V7_PORTS; do (exec 3<>/dev/tcp/127.0.0.1/$p) 2>/dev/null && o="$o $p"; done; echo $o; }
v7_snap_health() { [ "$DRY" = 1 ] && return 0; mkdir -p "$V7_RUN"; v7_up_ports > "$V7_RUN/$SID.ports_before"; say "до этапа слушают порты: $(cat "$V7_RUN/$SID.ports_before")"; }
# после этапа: каждый порт, что слушал ДО, должен слушать (кроме перечисленных в $1 - намеренно остановленных)
v7_health_regress() {
  [ "$DRY" = 1 ] && return 0
  local before now p bad=""; before=$(cat "$V7_RUN/$SID.ports_before" 2>/dev/null); now=" $(v7_up_ports) "
  for p in $before; do case " ${1:-} " in *" $p "*) continue;; esac; case "$now" in *" $p "*) ;; *) bad="$bad $p";; esac; done
  [ -z "$bad" ] || { say "после этапа не слушают порты:$bad"; return 1; }
}
v7_chat_probe() {   # $1 mode ; печатает JSON-строку; rc 0 = ответ непустой
  python3 "$V7_TOOLS/probe.py" chat --url "${V7_GW:-http://127.0.0.1:8082}" --mode "${1:-fast}" --max-tokens "${2:-24}" --timeout "${3:-90}" ${4:+--prompt "$4"}
}
v7_s03_db() { local c; for c in "${S03_DB:-}" "$V7_HOME/memory/s03.db" "$V7_STATE/s03.sqlite"; do [ -n "$c" ] && [ -f "$c" ] && { echo "$c"; return; }; done; echo "$V7_HOME/memory/s03.db"; }
v7_dsp_live() { pgrep -f 'nox_dispatcher\.py run' >/dev/null 2>&1; }
v7_dsp() { DSP_HOME="$V7_HOME" python3 "$V7_DSP/current/nox_dispatcher.py" "$@"; }
v7_flag() { python3 "$V7_TOOLS/gw_env.py" flags "$@" >/dev/null; }
v7_flags_to_local() { v7_dsp_live && python3 "$V7_TOOLS/gw_env.py" local-json --services-json "$V7_DSP/current/services.json" --local-json "$V7_DSP/local.json" --apply >/dev/null; }
# v7_restart gateway|web|core : через диспетчер, если он живой (флаги вшиты в local.json), иначе gw_env.py с прежним окружением
v7_restart() {
  local n="$1"
  if [ "$DRY" = 1 ]; then echo "[dry-run] restart $n (через DSP если жив, иначе gw_env.py)"; return 0; fi
  if v7_dsp_live; then v7_flags_to_local; v7_dsp restart "$n" >/dev/null 2>&1; sleep 3; return 0; fi
  case "$n" in
    gateway) python3 "$V7_TOOLS/gw_env.py" restart --match 'python3 .*gateway\.py' --cwd "$V7_CTL/glm53" --log "$V7_LOGS/gateway.log" --health http://127.0.0.1:8082/health \
               --env-default "PYTHONPATH=$V7_CTL" --env-default "NOX_UPSTREAM=http://127.0.0.1:8081" --env-default "NOX_FAST_UPSTREAM=http://127.0.0.1:8083" --env-default NOX_TWO_STAGE=1 --env-default NOX_SOUL=1 --env-default NOX_EMOTION=1 \
               -- python3 "$V7_CTL/glm53/gateway.py";;
    recall)  python3 "$V7_TOOLS/gw_env.py" restart --match 'qs6\.recall_server' --cwd "$V7_CTL" --log "$V7_LOGS/recall_api.log" --health http://127.0.0.1:8095/health \
               --env-default "PYTHONPATH=$V7_CTL" --env-default "NOX_MEMORY_DB=$(v7_s03_db)" --env-default NOX_RECALL_PORT=8095 --env-default NOX_SOUL=1 --env-default NOX_EMOTION=1 \
               --env-default "NOX_EVENTS=$V7_HOME/memory/events.jsonl" -- python3 -m qs6.recall_server;;
    rte)     python3 "$V7_TOOLS/gw_env.py" restart --match 'rte_server\.py' --cwd "$V7_W/rte" --log "$V7_LOGS/rte.log" --health http://127.0.0.1:8084/v1/rte/health \
               --env-default NOX_GATEWAY_URL=http://127.0.0.1:8082 --env-default NOX_DEEP_SLOTS_URL=http://127.0.0.1:8081 --env-default NOX_FAST_UPSTREAM=http://127.0.0.1:8083 \
               --env-default "NOX_STATE=$V7_STATE" -- python3 "$V7_W/rte/rte_server.py";;
    web)     python3 "$V7_TOOLS/gw_env.py" restart --match 'web_server\.py' --log "$V7_LOGS/web_server.log";;
    core)    python3 "$V7_TOOLS/gw_env.py" restart --match 'wow7/brain/nox_core\.py' --cwd "$V7_W/brain" --log "$V7_LOGS/core.log" --health "http://127.0.0.1:${NOX_CORE_PORT:-8090}/health" \
               --env-default "NOX_WOW7=$V7_W" --env-default "NOX_STATE=$V7_STATE" --env-default "NOX_RECEIPTS=$V7_RC" --env-default "NOX_TRACE_DIR=$V7_STATE/core_trace" -- python3 "$V7_W/brain/nox_core.py";;
    *) die "неизвестный сервис $n";;
  esac
}
# python-тесты установленного модуля на месте: v7_test_mod mod [test_module...]; rc 0 = зелёные
v7_test_mod() {
  local m="$1"; shift; local d="$V7_W/$m" t rc=0
  [ "$DRY" = 1 ] && { echo "[dry-run] unittest $m ${*:-(test_*.py)}"; return 0; }
  [ -d "$d" ] || return 0
  local tests=("$@"); [ ${#tests[@]} -eq 0 ] && for t in "$d"/test_*.py "$d"/tests/test_*.py; do [ -f "$t" ] && tests+=("$t"); done
  for t in "${tests[@]:-}"; do [ -n "$t" ] || continue; local dd; dd=$(dirname "$t"); [ -f "$t" ] || t="$d/$t.py"
    (cd "$dd" && NOX_WOW7="$V7_W" NOX_WOW_SRC="$V7_W" timeout 600 python3 -B -W ignore -m unittest "$(basename "$t" .py)" >"$V7_LOGS/$SID.test_$m.log" 2>&1) || { say "тесты $m красные: $V7_LOGS/$SID.test_$m.log"; tail -5 "$V7_LOGS/$SID.test_$m.log"; rc=1; }
  done; return $rc
}

v7_ld() {           # LD_LIBRARY_PATH для llama.cpp (как в start_glm_best.sh)
  local l; l=$(dirname "$(find /usr/local /usr/lib -name libcublas.so.12 2>/dev/null | head -1)" 2>/dev/null)
  export LD_LIBRARY_PATH="$l:/usr/local/cuda/lib64:$V7_HOME/llama.cpp/build/bin:${LD_LIBRARY_PATH:-}"
}

# ---------------------------------------------------------------- каркас этапа
v7_status() {
  [ -f "$V7_RC/$SID.json" ] && cat "$V7_RC/$SID.json" || echo "квитанции $V7_RC/$SID.json нет"
  local pf="$V7_RUN/$SID.pid"; [ -f "$pf" ] && { kill -0 "$(cat "$pf")" 2>/dev/null && echo "процесс $(cat "$pf") ЖИВ" || echo "процесс $(cat "$pf") завершён"; }
  [ -f "$V7_LOGS/$SID.log" ] && { echo "--- хвост лога $V7_LOGS/$SID.log"; tail -n 25 "$V7_LOGS/$SID.log" | cut -c1-240; }
}
v7_main() {
  v7_parse "${V7_ARGV[@]:-}"
  [ "$STATUS" = 1 ] && { v7_status; exit 0; }
  if [ "$DRY" = 1 ]; then say "DRY-RUN: $TITLE (LONG=$LONG)"; stage_plan; v7_receipt dry plan=dry-run; say "DRY-RUN готов: ничего не изменено"; exit 0; fi
  mkdir -p "$V7_LOGS" "$V7_RUN" "$V7_RC" "$V7_BK/$SID"
  if [ "$LONG" = 1 ] && [ "$FG" = 0 ]; then
    local B="$V7_RUN/bin"; mkdir -p "$B"; cp "$V7_SELF" "$B/$(basename "$V7_SELF")"; cp "$V7_LIB" "$B/lib_v7.sh"
    v7_receipt running started="$(date -Is)"
    V7_SELF="$B/$(basename "$V7_SELF")" nohup setsid bash "$B/$(basename "$V7_SELF")" "${V7_ARGV[@]}" --fg >> "$V7_LOGS/$SID.log" 2>&1 < /dev/null &
    echo $! > "$V7_RUN/$SID.pid"; echo "$SID: запущено в фоне pid=$! лог=$V7_LOGS/$SID.log; проверка: bash $V7_SELF --status"; exit 0
  fi
  exec 9>"$V7_RUN/deploy.lock"; flock -n 9 || die "другой этап V7 ещё идёт (lock $V7_RUN/deploy.lock)" 4
  echo $$ > "$V7_RUN/$SID.pid"
  command -v python3 >/dev/null && command -v curl >/dev/null || die "нужны python3 и curl" 5
  local fgb; fgb=$(df -BG --output=avail "$V7_HOME" 2>/dev/null | tail -1 | tr -dc 0-9); [ "${fgb:-99}" -ge 3 ] || die "на диске меньше 3 ГБ" 5
  if [ "$ROLLBACK" = 1 ]; then say "ОТКАТ по запросу"; v7_bk_restore || true; stage_rollback || true; v7_receipt rolled_back reason=manual; exit 0; fi
  v7_stop_active && [ "$FORCE" = 0 ] && [ "${STOP_OK:-0}" != 1 ] && die "активен STOP (/run/nox/STOP или $V7_HOME/STOP); --force чтобы идти" 6
  v7_receipt running started="$(date -Is)"
  v7_bk_begin; v7_snap_health
  mkdir -p "$V7_RUN"; v7_sync_set deploy >/dev/null 2>&1 || true
  if stage_apply; then
    if stage_health; then v7_receipt ok finished="$(date -Is)" ${V7_RESULT:+result="$V7_RESULT"}; say "ГОТОВО"; exit 0; fi
    say "здоровье НЕ прошло"
  else say "stage_apply провалился"; fi
  say "ОТКАТ"; v7_bk_restore || true; stage_rollback || true
  v7_receipt rolled_back reason="apply/health failed" ${V7_RESULT:+result="$V7_RESULT"}; exit 1
}
