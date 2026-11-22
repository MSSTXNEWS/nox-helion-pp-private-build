#!/usr/bin/env bash
# S1_03 СКОРОСТЬ GLM-5.3: рычаги ПО ОДНОМУ через ab_bench (потоки, -ub/op-offload порог, cache-reuse, cache-ram, NUMA, ngram; MTP только если OPT-02 даёт worth_draft),
# системные рычаги (numa_balancing, THP) отдельными A/B, победитель -> /root/nox/gpu_tier/GLM_ARGS.best (+ winner.json для DSP), перезапуск GLM, KV души на диск,
# замер TTFT/pp/tg ДО и ПОСЛЕ -> /root/nox/state/v7/SPEED_REPORT.json (копия в receipts/V7-03.speed.json). Метка #S1. Идёт в фон, часы.
# Не трогает репо gpu_tier/GLM_ARGS (свип другого исполнителя) и glm.args. Запреты: --no-mmap/--mlock, KV-квант (в ab_bench/start_glm_best), одна главная модель.
# Отказ (rc 7) если идёт свип gpu_tier (bench_glm/llama-bench/glm_sweep) - --force только по слову владельца. Желательно тихие часы 23-08 МСК (GLM будет остановлен на время A/B): иначе --allow-daytime.
# Флаги: --dry-run --fg --status --rollback --force --allow-daytime ; --no-sys (без системных рычагов) --only L01_threads_phys,... (подмножество рычагов)
SID=V7-03; STAGE_NO=3; TITLE="Скорость GLM (A/B по одному рычагу)"; LONG=1
OUT="$V7_RUN/speed"; ABOUT="$V7_LOGS/spd_ab"; WIN="$ABOUT/winner.json"; BEST="$V7_HOME/gpu_tier/GLM_ARGS.best"; BIN="$V7_HOME/llama.cpp/build/bin"
stage_plan() {
  echo "0. отказ, если свип gpu_tier активен; предупреждение вне тихих часов; бэкап winner.json/glm.args/GLM_ARGS.best/local.json"
  echo "1. набор deploy,spd,opt; BEFORE: ab_bench --attach :8081 -> speed/before"
  echo "2. STOP-маркер ($V7_HOME/STOP, снимается в конце): останов GLM; OPT-02 зонд llama-bench -p 1,2,4,8,16 -> receipts/OPT-02.json (решение по MTP/DFlash2)"
  echo "3. matrix_v7.json = SPD/matrix.json: порядок L01,L02,L03,L08,L09,L10,L12,L07 (+L05/L06 MTP только при worth_draft), без L04/L11 (свип) и X01; base = живые флаги"
  echo "4. системные рычаги по одному (A/B base-only каждый): numa_balancing=0 (numa_tune --apply), THP=madvise|always, если доступны на запись; принятые остаются, отклонённые откатываются"
  echo "5. ab_bench --accumulate (порт 8091) -> $WIN ; один рычаг за раз, принят при score>=1.05, качество>=0.9, tg не хуже -10%"
  echo "6. победитель -> $BEST (+ .env), local.json DSP glm.env; start_glm_best.sh (запреты, --slot-save-path, --cache-reuse, прогрев KV души); health"
  echo "7. AFTER: ab_bench --attach :8081; TTFT души холодный/после soul_kv_warm; speed_report.py -> SPEED_REPORT.json; regressed => откат"
}
cleanup_stop() { [ "${V7_STOP_MINE:-0}" = 1 ] && rm -f "$V7_HOME/STOP" && V7_STOP_MINE=0; }
glm_args_live() { for f in "$V7_HOME/gpu_tier/GLM_ARGS.best" "$V7_HOME/gpu_tier/glm.args"; do [ -s "$f" ] && { cat "$f"; return; }; done; python3 -I - "$V7_W/spd/matrix.json" <<'PY'
import json, shlex, sys
print(" ".join(shlex.quote(x) for x in json.load(open(sys.argv[1]))["base"]))
PY
}
stop_glm() {
  local p
  for p in $(pgrep -x llama-server); do tr '\0' ' ' < /proc/$p/cmdline | grep -qE -- '--port 8081( |$)' && kill "$p"; done
  local i; for i in $(seq 1 40); do pgrep -f 'llama-server.*--port 8081' >/dev/null || return 0; sleep 2; done; return 1
}
ab() {  # ab OUTDIR args... ; PATH/LD уже выставлены
  local o="$1"; shift; python3 "$V7_W/spd/ab_bench.py" --bin "$BIN/llama-server" --out "$o" --port 8091 "$@"
}
sys_lever() {   # name apply_cmd revert_cmd : A/B base-only против опорного
  local n="$1" ap="$2" rv="$3" o="$OUT/sys_$n"
  say "системный рычаг $n"; mkdir -p "$o"
  eval "$ap" || { say "$n: не применилось (нет прав) - пропуск"; echo "{\"$n\":\"skip: no permission\"}" >> "$OUT/sys_log.jsonl"; return 0; }
  ab "$o" --matrix "$OUT/matrix_v7.json" --only base || { eval "$rv"; say "$n: замер не прошёл, откатил"; return 0; }
  if python3 "$V7_TOOLS/ab_verdict.py" --spd "$V7_W/spd" --matrix "$OUT/matrix_v7.json" --ref "$OUT/ref/results.json" --cand "$o/results.json" > "$o/verdict.json"; then
    say "$n: ПРИНЯТ $(cat "$o/verdict.json")"; echo "{\"$n\":\"accepted\"}" >> "$OUT/sys_log.jsonl"; REVERT_SYS="$REVERT_SYS; $rv"
  else say "$n: отклонён $(cat "$o/verdict.json")"; eval "$rv"; echo "{\"$n\":\"rejected\"}" >> "$OUT/sys_log.jsonl"; fi
}
stage_apply() {
  v7_sweep_active && [ "$FORCE" = 0 ] && die "идёт свип gpu_tier (bench/sweep процессы) - не мешаю" 7
  v7_quiet || [ "$ALLOW_DAY" = 1 ] || die "не тихие часы (23-08 МСК): GLM будет остановлен на время A/B; --allow-daytime чтобы всё равно" 8
  local s; for s in spd opt; do v7_sync_set "$s" || return 1; done; v7_links
  mkdir -p "$OUT" "$ABOUT"; v7_ld; export PATH="$BIN:$PATH"; REVERT_SYS=":"
  for f in "$WIN" "$V7_HOME/gpu_tier/glm.args" "$BEST" "$BEST.env" "$V7_DSP/local.json"; do v7_bk_file "$f"; done
  cp /proc/sys/kernel/numa_balancing "$OUT/numa_balancing.before" 2>/dev/null; cp /sys/kernel/mm/transparent_hugepage/enabled "$OUT/thp.before" 2>/dev/null
  trap cleanup_stop EXIT
  # --- BEFORE
  local BASEF="$OUT/base_args.txt"; glm_args_live > "$BASEF"; say "базовые флаги: $(cat "$BASEF")"
  if v7_http http://127.0.0.1:8081/health 5; then ab "$OUT/before" --attach http://127.0.0.1:8081 --matrix "$V7_W/spd/matrix.json" || say "BEFORE не снят"; else say "GLM не жив - BEFORE пуст (в отчёте будет no_data)"; fi
  # --- останов GLM под A/B
  [ -e "$V7_HOME/STOP" ] || { touch "$V7_HOME/STOP"; V7_STOP_MINE=1; }     # замораживает перезапуски DSP на время A/B; чужой STOP не трогаем
  stop_glm || { say "GLM не остановился"; return 1; }
  # --- OPT-02
  python3 "$V7_TOOLS/opt02_probe.py" --bench "$BIN/llama-bench" --args "$(cat "$BASEF")" --out "$V7_RC/OPT-02.json" || say "OPT-02: зонд не отработал (MTP не тестируем)"
  local MTP=""; python3 -I -c 'import json,sys;sys.exit(0 if json.load(open(sys.argv[1])).get("worth_draft") else 1)' "$V7_RC/OPT-02.json" 2>/dev/null && MTP="--mtp"
  python3 "$V7_TOOLS/make_matrix.py" --src "$V7_W/spd/matrix.json" --out "$OUT/matrix_v7.json" --base-from "$BASEF" $MTP || return 1
  # --- опорный base-only
  ab "$OUT/ref" --matrix "$OUT/matrix_v7.json" --only base || { say "base не поднялся под ab_bench - стоп"; return 1; }
  # --- системные рычаги
  if ! has_extra --no-sys; then
    sys_lever numa_balancing "[ \"\$(cat /proc/sys/kernel/numa_balancing 2>/dev/null)\" = 0 ] || { [ -w /proc/sys/kernel/numa_balancing ] && echo 0 > /proc/sys/kernel/numa_balancing; } && [ \"\$(cat /proc/sys/kernel/numa_balancing)\" = 0 ] && [ \"\$(cat $OUT/numa_balancing.before 2>/dev/null)\" != 0 ]" "echo \$(cat $OUT/numa_balancing.before) > /proc/sys/kernel/numa_balancing"
    sys_lever thp_madvise "[ -w /sys/kernel/mm/transparent_hugepage/enabled ] && echo madvise > /sys/kernel/mm/transparent_hugepage/enabled && ! grep -q '\\[madvise\\]' $OUT/thp.before" "echo \$(sed 's/.*\\[\\(.*\\)\\].*/\\1/' $OUT/thp.before) > /sys/kernel/mm/transparent_hugepage/enabled"
  fi
  # --- накопительный прогон рычагов
  local ONLY=""; ONLY=$(extra_val --only) && ONLY="--only $ONLY"
  ab "$ABOUT" --matrix "$OUT/matrix_v7.json" --accumulate $ONLY || { say "ab_bench accumulate завершился с ошибкой"; return 1; }
  # --- победитель -> GLM_ARGS.best
  python3 -I - "$WIN" "$BEST" <<'PY' || return 1
import json, shlex, sys
w = json.load(open(sys.argv[1])); a = w.get("args")
if not a: sys.exit("в winner.json нет args")
open(sys.argv[2], "w").write(" ".join(shlex.quote(x) for x in a) + "\n")
open(sys.argv[2] + ".env", "w").write("".join("%s=%s\n" % kv for kv in (w.get("env") or {}).items()))
print("победитель %s -> %s" % (w.get("id"), sys.argv[2]))
PY
  cp "$BEST" "$BEST.env" "$OUT/" 2>/dev/null
  local envs; envs=$(sed 's/^/--set /' "$BEST.env" | tr '\n' ' ')
  [ -n "$envs" ] && python3 "$V7_TOOLS/gw_env.py" local-env --local-json "$V7_DSP/local.json" --service glm $envs >/dev/null
  # --- перезапуск GLM победителем (start_glm_best проверяет запреты, ставит slot-save/cache-reuse), прогрев души отдельно ради замера
  WIN="$WIN" bash "$V7_W/spd/start_glm_best.sh" --no-warm || { say "start_glm_best провалился rc=$?"; return 1; }
  cleanup_stop
  # --- AFTER
  ab "$OUT/after" --attach http://127.0.0.1:8081 --matrix "$OUT/matrix_v7.json" || say "AFTER не снят"
  local SOUL="$V7_STATE/soul_prompt_ru.txt"; [ -f "$V7_W/prime/soul_prime_v3.txt" ] && [ -f "$V7_CTL/glm53/soul_prime_v3.txt" ] && SOUL="$V7_CTL/glm53/soul_prime_v3.txt"; [ -f "$SOUL" ] || SOUL="$V7_W/prime/soul_prime_v3.txt"
  local cold warm mode="warm"; cold=$(python3 "$V7_TOOLS/probe.py" completion --url http://127.0.0.1:8081 --system-file "$SOUL" --n 4 2>/dev/null | tail -1)
  bash "$V7_W/spd/soul_kv_warm.sh" --soul "$SOUL" auto >"$OUT/soul_kv.out" 2>&1 && grep -qi restore "$OUT/soul_kv.out" && mode="restore"
  warm=$(python3 "$V7_TOOLS/probe.py" completion --url http://127.0.0.1:8081 --system-file "$SOUL" --n 4 2>/dev/null | tail -1)
  python3 -I - "$OUT/soul.json" "$cold" "$warm" "$mode" <<'PY'
import json, sys
def g(s):
    try: return json.loads(s).get("ttft_s")
    except Exception: return None
json.dump({"cold_ttft_s": g(sys.argv[2]), "warm_ttft_s": g(sys.argv[3]), "mode": sys.argv[4]}, open(sys.argv[1], "w"))
PY
  local fast=""; [ -f "$V7_RUN/baseline/fast/results.json" ] && fast="--fast $V7_RUN/baseline/fast/results.json"
  python3 "$V7_TOOLS/speed_report.py" --before "$OUT/before/results.json" --after "$OUT/after/results.json" --ab "$ABOUT/results.json" --opt02 "$V7_RC/OPT-02.json" --soul "$OUT/soul.json" --out "$V7_RUN/SPEED_REPORT.json" | tee "$OUT/report.line"
  cp "$V7_RUN/SPEED_REPORT.json" "$V7_RC/V7-03.speed.json"; V7_RESULT=$(cat "$OUT/report.line" | tr -d '"')
  return 0
}
stage_health() {
  v7_http http://127.0.0.1:8081/health 10 || { say "GLM :8081 не здоров"; return 1; }
  v7_health_regress 8091 || return 1
  python3 -I -c 'import json,sys;r=json.load(open(sys.argv[1]));print("verdict",r["verdict"]);sys.exit(1 if r["rollback_recommended"] else 0)' "$V7_RUN/SPEED_REPORT.json"
}
stage_rollback() {
  eval "${REVERT_SYS:-:}" 2>/dev/null
  python3 "$V7_TOOLS/gw_env.py" local-env --local-json "$V7_DSP/local.json" --service glm --clear >/dev/null 2>&1
  for p in $(pgrep -x llama-server); do tr '\0' ' ' < /proc/$p/cmdline | grep -qE -- '--port (8081|8091)( |$)' && kill "$p"; done; sleep 5
  bash "$V7_W/spd/start_glm_best.sh" --no-warm || say "ВНИМАНИЕ: GLM не поднялся прежними флагами - запусти gpu_tier/run.sh glmstart или DSP: nox_dispatcher.py restart glm"
  cleanup_stop
  return 0
}

V7_SELF="${BASH_SOURCE[0]}"; V7_SELF_DIR=$(cd "$(dirname "$V7_SELF")" && pwd)
if [ ! -f "$V7_SELF_DIR/lib_v7.sh" ]; then V7_SELF_DIR=/tmp/v7deploy; mkdir -p "$V7_SELF_DIR"; curl -fsSL "${V7_RAW:-https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main}/nox-control/wow7/deploy/lib_v7.sh?cb=$RANDOM" -o "$V7_SELF_DIR/lib_v7.sh" || { echo "не скачался lib_v7.sh" >&2; exit 9; }; fi
. "$V7_SELF_DIR/lib_v7.sh"

v7_main
