#!/usr/bin/env bash
# S1_06 ОРГАНЫ: EMO (эмоции/влечения), CON (я-модель, рабочее пространство, внутренний цикл + мост), TRAITS (64 ползунка, ночной цикл), PER (личность/взгляды/развитие),
# ADV (внешние бесплатные советники; ключи ТОЛЬКО в /root/nox/secrets/advisors.env, создаётся пустым, заполняет владелец), WORLD (ленты, self_atlas). Метка #S1.
# Каждый орган изолирован: красные тесты -> файлы ЭТОГО органа откатываются, орган пропущен (в квитанции organs{}); обязательны EMO и CON.
# Откат всего этапа: --rollback. Флаги: --dry-run --fg --status --rollback ; --only emo,con,per,traits,adv,world ; --no-inner (не запускать внутренний цикл CON)
SID=V7-06; STAGE_NO=6; TITLE="Органы: EMO CON TRAITS PER ADV WORLD"; LONG=0
ORGANS="emo con per traits adv world"
stage_plan() {
  echo "для каждого органа: sync набора, unittest на месте, при красных - откат файлов органа"
  echo "emo: wow7/emo (NOX_EMOTION=1 уже в env шлюза); con: wow7/con + bridge/con_hooks.py + патч bridge/nox_bridge.py, ссылка /root/nox/src/con, NOX_INNER=1, inner_loop --daemon --interval 300 (под DSP или nohup)"
  echo "per: wow7/per; traits: wow7/traits (+ seed 64, nightly из «сна», веб-панель - S1_07); adv: deploy_adv_s1.sh --port 8099 --no-system -> ADV-01.json, ключи в $V7_HOME/secrets/advisors.env"
  echo "world: cron ленты (*/30) и self_atlas scan (7 * * * *), unittest world; затем перезапуск шлюза и моста; здоровье"
}
declare -A ORG
want() { local o; o=$(extra_val --only) || return 0; case ",$o," in *",$1,"*) return 0;; *) return 1;; esac; }
organ_ok() { ORG[$1]=ok; say "орган $1: OK"; }
organ_skip() { ORG[$1]="skipped: $2"; say "орган $1 ПРОПУЩЕН: $2"; local ch="$V7_RUN/$SID.$3.changed"; [ -f "$ch" ] && v7_bk_restore "$ch"; }
do_emo()    { v7_sync_set emo || return 1; v7_links; v7_test_mod emo; }
do_per()    { v7_sync_set per || return 1; v7_links; v7_test_mod per; }
do_traits() { v7_sync_set traits || return 1; v7_links; v7_test_mod traits && python3 "$V7_W/traits/nightly.py" --dry-run >"$V7_RUN/traits_dry.out" 2>&1; }
do_con() {
  v7_sync_set con || return 1; v7_sync_set conbridge || return 1; v7_links
  v7_place_dir "$V7_W/con" "$V7_HOME/src/con"; v7_test_mod con || return 1
  v7_flag set NOX_INNER=1
  pgrep -f 'nox_bridge\.py' >/dev/null && python3 "$V7_TOOLS/gw_env.py" restart --match 'nox_bridge\.py' --log "$V7_LOGS/bridge.log" >/dev/null 2>&1
  has_extra --no-inner && return 0
  if v7_dsp_live; then v7_dsp start con_inner >/dev/null 2>&1; else
    python3 "$V7_TOOLS/gw_env.py" restart --match 'nox_inner_loop\.py --daemon' --cwd "$V7_W/con" --log "$V7_LOGS/con_inner.log" -- python3 nox_inner_loop.py --daemon --interval 300 >/dev/null; fi
}
do_adv() {
  v7_sync_set adv || return 1; v7_sync_set world || return 1; v7_links; v7_test_mod adv || return 1
  SRC="$V7_W/adv" bash "$V7_W/adv/deploy_adv_s1.sh" --src "$V7_W/adv" --root "$V7_HOME" --port 8099 --no-system > "$V7_RUN/adv_install.out" 2>&1 || { tail -5 "$V7_RUN/adv_install.out"; return 1; }
  chmod 600 "$V7_HOME/secrets/advisors.env" 2>/dev/null; tail -1 "$V7_RUN/adv_install.out" | cut -c1-300
}
do_world() {
  v7_sync_set world || return 1; v7_links; v7_test_mod world || return 1
  local W="$V7_W/world"; v7_bk_file /etc/cron.d/nox-world
  [ -d /etc/cron.d ] && printf '*/30 * * * * root cd %s && NOX_STATE=%s python3 world_feed.py run --beliefs >>%s/world_feed.log 2>&1\n7 * * * * root cd %s && python3 self_atlas.py scan >>%s/self_atlas.log 2>&1\n' "$W" "$V7_STATE" "$V7_LOGS" "$W" "$V7_LOGS" > /etc/cron.d/nox-world
  (cd "$W" && NOX_STATE="$V7_STATE" python3 self_atlas.py scan >"$V7_RUN/atlas.out" 2>&1) || return 1
}
stage_apply() {
  local o; v7_bk_file "$V7_STATE/v7_flags.json"; v7_sync_set common || return 1
  for o in $ORGANS; do
    want "$o" || { ORG[$o]="not requested"; continue; }
    if [ "$DRY" = 1 ]; then continue; fi
    if "do_$o"; then organ_ok "$o"; else organ_skip "$o" "ошибка/красные тесты" "$o"; case "$o" in emo|con) say "обязательный орган $o не встал"; return 1;; esac; fi
  done
  v7_restart gateway || return 1
  V7_RESULT=$(for o in $ORGANS; do printf '%s=%s;' "$o" "${ORG[$o]:-?}"; done)
  v7_receipt running organs="$(python3 -I -c 'import json,sys;print(json.dumps(dict(kv.split("=",1) for kv in sys.argv[1].split(";") if kv)))' "$V7_RESULT")"
}
stage_health() { v7_health_regress && v7_http http://127.0.0.1:8082/v1/nox/stats 10 && { v7_chat_probe fast 40 120 "привет" | tee "$V7_RUN/p6_hi.json" | cut -c1-200; grep -q '"ok": true' "$V7_RUN/p6_hi.json"; }; }
stage_rollback() { rm -f /etc/cron.d/nox-world; v7_flag unset NOX_INNER; pkill -f 'nox_inner_loop\.py --daemon' 2>/dev/null; v7_restart gateway; return 0; }

V7_SELF="${BASH_SOURCE[0]}"; V7_SELF_DIR=$(cd "$(dirname "$V7_SELF")" && pwd)
if [ ! -f "$V7_SELF_DIR/lib_v7.sh" ]; then V7_SELF_DIR=/tmp/v7deploy; mkdir -p "$V7_SELF_DIR"; curl -fsSL "${V7_RAW:-https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main}/nox-control/wow7/deploy/lib_v7.sh?cb=$RANDOM" -o "$V7_SELF_DIR/lib_v7.sh" || { echo "не скачался lib_v7.sh" >&2; exit 9; }; fi
. "$V7_SELF_DIR/lib_v7.sh"

v7_main
