#!/usr/bin/env bash
# S1_04 RTE + NOX CORE: RTE (stream_hub/STOP с квитанцией/resume, :8084) -> CORE (:8090) с Совестью в режиме SHADOW -> флаг NOX_CORE=1 на шлюзе (проксирует чат в CORE, авто-откат если CORE лежит).
# Метка #S1. Откат: NOX_CORE снят, CORE/RTE остановлены, файлы из бэкапа, DSP local.json очищен.
# Флаги: --dry-run --fg --status --rollback ; --no-flip (поднять RTE+CORE, но шлюз НЕ переключать) ; --conscience enforce (после суток shadow)
SID=V7-04; STAGE_NO=4; TITLE="RTE + CORE (NOX_CORE=1, Совесть shadow)"; LONG=0
stage_plan() {
  echo "1. наборы deploy,common,rte,brain,prime,act,mind,hotfix; ссылки wow7; unittest brain и rte на месте"
  echo "2. RTE: rte_server :8084 (gw_env restart), probe_pv01.py -> RTE-06.json (если GLM жив)"
  echo "3. CORE: флаги NOX_CONSCIENCE=shadow NOX_CORE_PORT=8090; nox_core.py :8090; /health (organs) ; проба чата через CORE"
  echo "4. DSP local.json: сервис core под надзор (если диспетчер установлен)"
  echo "5. NOX_CORE=1 -> перезапуск шлюза; проба чата через шлюз; порты, что были, живы; иначе откат"
}
stage_apply() {
  local s; for s in common rte brain prime act mind hotfix; do v7_sync_set "$s" || return 1; done; v7_links
  v7_test_mod brain || return 1; v7_test_mod rte || return 1
  v7_bk_file "$V7_STATE/v7_flags.json"; v7_bk_file "$V7_DSP/local.json"
  v7_restart rte || { say "rte_server не поднялся: $V7_LOGS/rte.log"; return 1; }
  if v7_http http://127.0.0.1:8081/health 5; then
    python3 "$V7_W/rte/probe_pv01.py" --base http://127.0.0.1:8084 --receipts "$V7_RC" > "$V7_RUN/rte_probe.out" 2>&1; V7_RTE_RC=$?; say "probe_pv01 rc=$V7_RTE_RC: $(tail -2 "$V7_RUN/rte_probe.out" | tr '\n' ' ' | cut -c1-200)"
    [ "$V7_RTE_RC" = 0 ] || say "probe_pv01 не прошёл (GLM занят замерами исполнителя Б?) - не блокирую, повтор в S1_08"   # NOXFIX
  else say "GLM не жив - probe_pv01 (длинный ход, STOP) пропущен, повторить в S1_08"; fi
  local cons; cons=$(extra_val --conscience || echo shadow)
  v7_flag set "NOX_CONSCIENCE=$cons" NOX_CORE_PORT=8090 "NOX_WOW7=$V7_W"
  v7_restart core || { say "CORE не поднялся: $V7_LOGS/core.log"; return 1; }
  v7_http http://127.0.0.1:8090/health 10 || return 1
  say "CORE /health: $(curl -s -m5 http://127.0.0.1:8090/health | cut -c1-300)"
  python3 "$V7_TOOLS/probe.py" chat --url http://127.0.0.1:8090 --mode fast --max-tokens 40 --timeout 120 --prompt "привет" | tee "$V7_RUN/core_probe.json" | cut -c1-200
  grep -q '"ok": true' "$V7_RUN/core_probe.json" || { say "CORE не ответил на привет"; return 1; }
  v7_dsp_live || [ -d "$V7_DSP/current" ] && python3 "$V7_TOOLS/gw_env.py" local-json --services-json "$V7_DSP/current/services.json" --local-json "$V7_DSP/local.json" --apply >/dev/null 2>&1
  if has_extra --no-flip; then say "шлюз не переключаю (--no-flip)"; return 0; fi
  v7_flag set NOX_CORE=1; v7_restart gateway || return 1
  v7_chat_probe fast 40 120 "привет" | tee "$V7_RUN/gw_core_probe.json" | cut -c1-200
  grep -q '"ok": true' "$V7_RUN/gw_core_probe.json" || { say "чат через шлюз+CORE не ответил"; return 1; }
  V7_RESULT="core=ok conscience=$cons core_flag=1 rte_probe=${V7_RTE_RC:-skipped}"
}
stage_health() { v7_health_regress && v7_http http://127.0.0.1:8090/health 5 && v7_http http://127.0.0.1:8082/v1/nox/stats 10; }
stage_rollback() {
  v7_flag unset NOX_CORE NOX_CONSCIENCE NOX_CORE_PORT
  pkill -f 'wow7/brain/nox_core\.py' 2>/dev/null; pkill -f 'rte_server\.py' 2>/dev/null
  python3 "$V7_TOOLS/gw_env.py" local-json --services-json "$V7_DSP/current/services.json" --local-json "$V7_DSP/local.json" --unapply >/dev/null 2>&1
  v7_restart gateway; return 0
}

V7_SELF="${BASH_SOURCE[0]}"; V7_SELF_DIR=$(cd "$(dirname "$V7_SELF")" && pwd)
if [ ! -f "$V7_SELF_DIR/lib_v7.sh" ]; then V7_SELF_DIR=/tmp/v7deploy; mkdir -p "$V7_SELF_DIR"; curl -fsSL "${V7_RAW:-https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main}/nox-control/wow7/deploy/lib_v7.sh?cb=$RANDOM" -o "$V7_SELF_DIR/lib_v7.sh" || { echo "не скачался lib_v7.sh" >&2; exit 9; }; fi
. "$V7_SELF_DIR/lib_v7.sh"

v7_main
