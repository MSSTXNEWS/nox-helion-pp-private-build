#!/usr/bin/env bash
# c400/s4: деплой brain (optlayer: телеметрия, кэш, судья, «мессир»; nox_intent) + набор opt, adv на S1; перезапуск ТОЛЬКО ядра :8090 (llama-server не трогается).
# Метка #S1. Откат автоматический (бэкап файлов -> восстановление, рестарт ядра).
set -- --fg --allow-daytime "$@"
SID=C400-S5; STAGE_NO=95; TITLE="c400: GENOME shadow"; LONG=0
stage_plan() { echo "sync brain,opt,adv; тесты brain; бэкап s03; рестарт core; живые пробы"; }
CH() { curl -s -m ${3:-120} -H 'content-type: application/json' -H "x-nox-conversation: $2" ${4:+-H "x-nox-eval: 1"} -d "$(python3 -I -c 'import json,sys;print(json.dumps({"messages":[{"role":"user","content":sys.argv[1]}],"max_tokens":200}))' "$1")" http://127.0.0.1:8090/v1/chat/completions; }
stage_apply() {
  local G=$V7_W/GENOME S=/root/nox/dl/v7/exec/nox_wow/GENOME
  [ -d $S ] || S=/root/nox/dl/v7/core/nox_wow/GENOME
  [ -d $G ] || { cp -r $S $G && say "GENOME скопирован из $S"; }
  ls $G | tr '\n' ' ' | cut -c1-300; echo
  (cd $G && ls test_*.py 2>/dev/null | head -20 | tr '\n' ' '; echo; NOX_WOW7=$V7_W NOX_STATE=/tmp/c400_gstate timeout 300 python3 -B -W ignore -m unittest discover -s . -p 'test_*.py' 2>&1 | tail -4)
  NOX_GENOME=shadow v7_flag set NOX_GENOME=shadow
  v7_restart core || { say core-не-поднялся; return 1; }
  v7_http http://127.0.0.1:8090/health 15 || return 1
  local r; r=$(CH "привет" c400-genome 120 eval); say "chat: $(echo "$r" | python3 -I -c 'import json,sys;d=json.load(sys.stdin);print(d["choices"][0]["message"]["content"][:120], d["nox"]["trace"])' 2>&1 | tail -1)"
  echo "$r" | grep -q '"content"' || return 1
  P=$(ps -eo pid,args | grep 'wow7/brain/nox_core' | grep -v grep | head -1 | awk '{print $1}'); say "genome env: $(tr '\0' '\n' </proc/$P/environ | grep GENOME)"
  say "genome в sys.modules ядра: $(grep -l GENOME /root/nox/logs/core.log 2>/dev/null | head -1) $(tail -c 300 /root/nox/logs/core.log | tr '\n' ' ')"
  python3 -I - <<'PY'
import sys,os
sys.path.insert(0,os.environ.get('V7','/root/nox/repo/nox-control/wow7'))
try:
    from GENOME.core_adapter import GenomeAdapter; print('import adapter ok',GenomeAdapter)
except Exception as e: print('import fail',type(e).__name__,e)
PY
}
stage_health() { v7_http http://127.0.0.1:8090/health 5 && v7_http http://127.0.0.1:8082/v1/nox/stats 10; }
stage_rollback() { v7_restart core; return 0; }

V7_SELF="${BASH_SOURCE[0]}"; V7_SELF_DIR=$(cd "$(dirname "$V7_SELF")" && pwd)
V7_SELF_DIR=/tmp/v7deploy; mkdir -p "$V7_SELF_DIR"; curl -fsSL "${V7_RAW:-https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main}/nox-control/wow7/deploy/lib_v7.sh?cb=$RANDOM" -o "$V7_SELF_DIR/lib_v7.sh" || { echo "не скачался lib_v7.sh" >&2; exit 9; }
. "$V7_SELF_DIR/lib_v7.sh"
v7_main

