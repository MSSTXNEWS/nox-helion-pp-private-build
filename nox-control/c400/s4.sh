#!/usr/bin/env bash
# c400/s4: деплой brain (optlayer: телеметрия, кэш, судья, «мессир»; nox_intent) + набор opt, adv на S1; перезапуск ТОЛЬКО ядра :8090 (llama-server не трогается).
# Метка #S1. Откат автоматический (бэкап файлов -> восстановление, рестарт ядра).
set -- --fg --allow-daytime "$@"
SID=C400-S4; STAGE_NO=94; TITLE="c400: optlayer + intent в ядро"; LONG=0
stage_plan() { echo "sync brain,opt,adv; тесты brain; бэкап s03; рестарт core; живые пробы"; }
CH() { curl -s -m ${3:-120} -H 'content-type: application/json' -H "x-nox-conversation: $2" ${4:+-H "x-nox-eval: 1"} -d "$(python3 -I -c 'import json,sys;print(json.dumps({"messages":[{"role":"user","content":sys.argv[1]}],"max_tokens":200}))' "$1")" http://127.0.0.1:8090/v1/chat/completions; }
stage_apply() {
  local s; for s in brain opt adv; do v7_sync_set "$s" || return 1; done; v7_links
  v7_test_mod brain || return 1
  python3 -I - <<'PY'
import sqlite3,time
B='/root/nox/memory/backups/s03_pre_c400s4_%s.sqlite'%time.strftime('%Y%m%d_%H%M%S')
s=sqlite3.connect('file:/root/nox/memory/s03.db?mode=ro',uri=True); d=sqlite3.connect(B); s.backup(d); print('s03 backup',B)
PY
  v7_restart core || { say "core не поднялся: $V7_LOGS/core.log"; return 1; }
  v7_http http://127.0.0.1:8090/health 15 || return 1
  say "core opt: $(curl -s -m5 http://127.0.0.1:8090/health | python3 -I -c 'import json,sys;d=json.load(sys.stdin);print(d.get("opt"))' | cut -c1-300)"
  local r; r=$(CH "привет" c400-greet 120 eval); say "chat: $(echo "$r" | python3 -I -c 'import json,sys;print(json.load(sys.stdin)["choices"][0]["message"]["content"][:160])' 2>&1 | tail -1)"
  echo "$r" | grep -q '"content"' || return 1
  sleep 12
  r=$(CH "мессир спрашивает: как сервер?" c400-tele 120 eval); say "tele: $(echo "$r" | python3 -I -c 'import json,sys;d=json.load(sys.stdin);print(d["choices"][0]["message"]["content"][:420].replace("\n"," "),"| path",d["nox"]["path"])' 2>&1 | tail -1)"
  local u=http://127.0.0.1:8090/intent
  say "intent status: $(curl -s -m10 $u/status | cut -c1-200)"
  say "intent refuse: $(curl -s -m10 -H 'content-type: application/json' -d '{"option":"c400-check: красный фон","reason":"режет глаза ночью","context":["ночь"],"project":"c400-check"}' $u/choices | cut -c1-260)"
  say "intent read: $(curl -s -m10 "$u/choices/revisit?context=ночь" | cut -c1-200)"
}
stage_health() { v7_http http://127.0.0.1:8090/health 5 && v7_http http://127.0.0.1:8082/v1/nox/stats 10; }
stage_rollback() { v7_restart core; return 0; }

V7_SELF="${BASH_SOURCE[0]}"; V7_SELF_DIR=$(cd "$(dirname "$V7_SELF")" && pwd)
V7_SELF_DIR=/tmp/v7deploy; mkdir -p "$V7_SELF_DIR"; curl -fsSL "${V7_RAW:-https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main}/nox-control/wow7/deploy/lib_v7.sh?cb=$RANDOM" -o "$V7_SELF_DIR/lib_v7.sh" || { echo "не скачался lib_v7.sh" >&2; exit 9; }
. "$V7_SELF_DIR/lib_v7.sh"
v7_main
