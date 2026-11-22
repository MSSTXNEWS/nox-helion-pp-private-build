#!/usr/bin/env bash
# S1_08 ПРИЁМКА: PV-01 (ACT/pv01_e2e: быстрый маршрут, мини-чат, источник факта, правка, новая сессия, STOP с квитанцией) + RTE probe + eval_top (+ mind_bench если есть)
# + wake + итоговая квитанция /root/nox/receipts/LIVE-24H.json (чат отвечает: fast <=3 с, deep живой; STOP с квитанцией; память с источником; правка факта подтверждена; wake; квитанции V7-00..07).
# Метка #S1. Ничего не меняет в боевых флагах. Флаги: --dry-run --fg --status ; --no-eval (без eval_top) ; --with-mind (mind_bench dev) ; --pv01-url URL (по умолчанию веб :8091)
# LIVE-24H pass = переход к SELF/WORLD-охоте/SLP. Иначе в квитанции first_broken_link и список провалов.
SID=V7-08; STAGE_NO=8; TITLE="Приёмка PV-01 + eval_top + LIVE-24H"; LONG=1
PV_URL_DEFAULT="http://127.0.0.1:8091/?memory=/memory/api&stop=/v1/stop&stats=/v1/nox/stats&chat=/v1/chat/completions&timeout=90"
stage_plan() {
  echo "1. sync act,top,mind,deploy; 2. pv01_e2e.py --url <веб|шлюз> -> ACT-PV01.json; 3. probe_pv01.py (если RTE :8084) -> RTE-06.json"
  echo "4. eval_top.py run -> state/eval_top_<дата>.json (если не --no-eval); mind_bench.py run --split dev (--with-mind)"
  echo "5. wake: nox_dispatcher wake (я-модель+шина) ; 6. LIVE-24H.json: критерии + статусы V7-00..07"
}
stage_apply() {
  local s; for s in common act top mind; do v7_sync_set "$s" || return 1; done; v7_links
  local url; url=$(extra_val --pv01-url || echo "$PV_URL_DEFAULT"); D=$(date +%F)
  python3 "$V7_W/act/pv01_e2e.py" --url "$url" --receipt "$V7_RC/ACT-PV01.json" > "$V7_RUN/pv01.out" 2>&1; say "PV-01 rc=$? first_broken=$(python3 -I -c 'import json;print(json.load(open("'$V7_RC'/ACT-PV01.json")).get("first_broken_link"))' 2>/dev/null)"
  v7_http http://127.0.0.1:8084/v1/rte/health 3 && python3 "$V7_W/rte/probe_pv01.py" --base http://127.0.0.1:8084 --receipts "$V7_RC" > "$V7_RUN/rte_probe.out" 2>&1
  if ! has_extra --no-eval; then python3 "$V7_W/top/eval_top.py" --url "${V7_GW:-http://127.0.0.1:8082}" --json "$V7_STATE/eval_top_$D.json" > "$V7_RUN/eval_top.out" 2>&1; say "eval_top rc=$? : $(tail -3 "$V7_RUN/eval_top.out" | tr '\n' ' ' | cut -c1-240)"; fi
  if has_extra --with-mind && [ -f "$V7_W/mind/M4_BENCH/mind_bench.py" ]; then (cd "$V7_W/mind/M4_BENCH" && python3 mind_bench.py run --url "${V7_GW:-http://127.0.0.1:8082}" --split dev --out "$V7_STATE/mind_bench_$D.json" > "$V7_RUN/mind.out" 2>&1); say "mind_bench rc=$?"; fi
  v7_dsp_live || [ -d "$V7_DSP/current" ] && v7_dsp wake > "$V7_RUN/wake.out" 2>&1; say "wake: $(tail -1 "$V7_RUN/wake.out" 2>/dev/null | cut -c1-200)"
  python3 "$V7_TOOLS/probe.py" chat --url "${V7_GW:-http://127.0.0.1:8082}" --mode fast --max-tokens 24 --timeout 60 > "$V7_RUN/live_fast.json" 2>/dev/null
  v7_http http://127.0.0.1:8081/health 5 && python3 "$V7_TOOLS/probe.py" chat --url "${V7_GW:-http://127.0.0.1:8082}" --mode deep --max-tokens 8 --timeout "${V7_DEEP_TIMEOUT:-900}" > "$V7_RUN/live_deep.json" 2>/dev/null
  python3 "$V7_TOOLS/live24h.py" --receipts "$V7_RC" --state "$V7_STATE" --run "$V7_RUN" --out "$V7_RC/LIVE-24H.json" || { V7_RESULT="LIVE-24H: НЕ пройдена, см. $V7_RC/LIVE-24H.json"; return 0; }
  V7_RESULT="LIVE-24H: pass"
}
stage_health() { v7_health_regress; }     # приёмка не откатывает боевое: результат - в LIVE-24H.json (status ok = этап выполнен)
stage_rollback() { return 0; }

V7_SELF="${BASH_SOURCE[0]}"; V7_SELF_DIR=$(cd "$(dirname "$V7_SELF")" && pwd)
if [ ! -f "$V7_SELF_DIR/lib_v7.sh" ]; then V7_SELF_DIR=/tmp/v7deploy; mkdir -p "$V7_SELF_DIR"; curl -fsSL "${V7_RAW:-https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main}/nox-control/wow7/deploy/lib_v7.sh?cb=$RANDOM" -o "$V7_SELF_DIR/lib_v7.sh" || { echo "не скачался lib_v7.sh" >&2; exit 9; }; fi
. "$V7_SELF_DIR/lib_v7.sh"

v7_main
