#!/bin/bash
# SPD-03 start_glm_best: запуск GLM-5.3 с лучшими флагами (победитель ab_bench) ПОСЛЕ проверки ЗАПРЕТОВ. Метка #S1.
# Источник флагов (по приоритету): --args-file -> $WIN (winner.json от ab_bench) -> /root/nox/gpu_tier/glm.args -> встроенные безопасные.
# ЗАПРЕТЫ (отказ с кодом 6): --no-mmap/--mlock; KV не f16 (-ctk/-ctv/--cache-type-*); -c < 16384; вторая главная модель на другом порту.
# Использование: bash start_glm_best.sh [--dry-run] [--no-warm] [--port 8081] [--args-file F]
PORT=8081; DRY=0; WARM=1; AF=""
BIN=${LLAMA_BIN:-/root/nox/llama.cpp/build/bin/llama-server}
MODEL=${NOX_GLM_MODEL:-/root/nox/glm53/GLM-5.3-UD-Q4_K_XL-00001-of-00011.gguf}
WIN=${WIN:-/root/nox/logs/spd_ab/winner.json}
SLOTDIR=${SLOTDIR:-/root/nox/state/soul_kv}
RECEIPTS=${RECEIPTS:-/root/nox/receipts}; LOGDIR=${LOGDIR:-/root/nox/logs}
HERE=$(cd "$(dirname "$0")" && pwd)
while [ $# -gt 0 ]; do case "$1" in
  --dry-run) DRY=1;; --no-warm) WARM=0;; --port) PORT="$2"; shift;; --args-file) AF="$2"; shift;;
  *) echo "unknown $1" >&2; exit 2;; esac; shift; done
SAFE='-c 16384 -ngl 24 -ot exps=CPU -t 24 -tb 24 -fa on --parallel 1 -b 512 -ub 256 --no-op-offload --jinja --temp 1.0 --top-p 0.95 --min-p 0.01'
ARGS=""; ENVS=""; SRC=builtin
if [ -n "$AF" ] && [ -f "$AF" ]; then ARGS=$(cat "$AF"); SRC="$AF"
elif [ -f "$WIN" ]; then
  eval "$(python3 - "$WIN" <<'PY'
import json, shlex, sys
w = json.load(open(sys.argv[1]))
a = w.get("args") or []
e = w.get("env") or {}
print("ARGS=%s" % shlex.quote(" ".join(shlex.quote(x) for x in a)))
print("ENVS=%s" % shlex.quote(" ".join("%s=%s" % (k, shlex.quote(str(v))) for k, v in e.items())))
PY
)"; [ -n "$ARGS" ] && SRC="$WIN"
elif [ -f /root/nox/gpu_tier/glm.args ]; then ARGS=$(cat /root/nox/gpu_tier/glm.args); SRC=/root/nox/gpu_tier/glm.args; fi
[ -n "$ARGS" ] || ARGS="$SAFE"

# --- проверка ЗАПРЕТОВ
BAD=""
case " $ARGS " in *" --no-mmap "*|*" --no-mmap="*) BAD="$BAD [--no-mmap]";; esac
case " $ARGS " in *" --mlock "*) BAD="$BAD [--mlock]";; esac
for f in -ctk -ctv --cache-type-k --cache-type-v; do
  V=$(echo "$ARGS" | tr -s ' ' '\n' | awk -v f="$f" '$0==f{getline; print; exit}')
  [ -n "$V" ] && [ "$V" != "f16" ] && BAD="$BAD [KV $f $V без A/B качества]"
done
C=$(echo "$ARGS" | tr -s ' ' '\n' | awk '$0=="-c"||$0=="--ctx-size"{getline; print; exit}')
[ -n "$C" ] && [ "$C" -lt 16384 ] 2>/dev/null && BAD="$BAD [контекст $C < 16384]"
OTHER=$(pgrep -a -x llama-server | grep -i "glm" | grep -v -- "--port $PORT" | grep -v pgrep | cut -c1-120)
[ -n "$OTHER" ] && BAD="$BAD [уже есть другая главная модель на другом порту: $OTHER]"
if [ -n "$BAD" ]; then echo "ОТКАЗ (запреты):$BAD" >&2; exit 6; fi

# --- доп. флаги только если сборка поддерживает и их нет в наборе
EXTRA=""
H=""; [ -x "$BIN" ] && H=$("$BIN" --help 2>&1)
case " $ARGS " in *" --slot-save-path "*) ;; *) if [ $DRY -eq 1 ] || echo "$H" | grep -q -- "--slot-save-path"; then EXTRA="$EXTRA --slot-save-path $SLOTDIR"; fi;; esac
case " $ARGS " in *" --cache-reuse "*) ;; *) if [ $DRY -eq 1 ] || echo "$H" | grep -q -- "--cache-reuse"; then EXTRA="$EXTRA --cache-reuse 256"; fi;; esac
CMD="$ENVS $BIN -m $MODEL --host 127.0.0.1 --port $PORT $ARGS$EXTRA"

if [ $DRY -eq 1 ]; then
  echo "DRY источник флагов: $SRC"; echo "DRY запреты: OK"; echo "DRY команда: $CMD"
  echo "DRY: остановлю только процесс на порту $PORT, подожду /health до 25 мин, затем soul_kv_warm.sh auto (WARM=$WARM); квитанция $RECEIPTS/SPD-03.json"; exit 0
fi
mkdir -p "$SLOTDIR" "$RECEIPTS" "$LOGDIR"
L=$(dirname "$(find /usr/local /usr/lib -name libcublas.so.12 2>/dev/null | head -1)")
export LD_LIBRARY_PATH="$L:/usr/local/cuda/lib64:$(dirname "$BIN"):$LD_LIBRARY_PATH"
for P in $(pgrep -x llama-server); do tr '\0' ' ' < /proc/$P/cmdline | grep -qE -- "--port $PORT( |$)" && kill "$P"; done; sleep 3
T0=$(date +%s)
# shellcheck disable=SC2086
nohup setsid env $CMD >> "$LOGDIR/glm_server.log" 2>&1 < /dev/null &
OK=0; for i in $(seq 1 375); do sleep 4; curl -fs -m3 "http://127.0.0.1:$PORT/health" 2>/dev/null | grep -q ok && { OK=1; break; }; done
LOAD=$(( $(date +%s) - T0 ))
WR=skipped
if [ $OK -eq 1 ] && [ $WARM -eq 1 ] && [ -f "$HERE/soul_kv_warm.sh" ]; then bash "$HERE/soul_kv_warm.sh" --port "$PORT" auto >> "$LOGDIR/soul_kv_warm.log" 2>&1 && WR=ok || WR=failed; fi
python3 - "$RECEIPTS/SPD-03.json" "$SRC" "$ARGS$EXTRA" "$ENVS" "$OK" "$LOAD" "$WR" <<'PY'
import json, sys, time
p, src, args, envs, ok, load, wr = sys.argv[1:8]
json.dump({"id": "SPD-03", "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "args_source": src, "args": args, "env": envs,
           "bans_checked": True, "healthy": ok == "1", "load_seconds": int(load), "soul_kv": wr}, open(p, "w"), ensure_ascii=False, indent=1)
PY
echo "healthy=$OK load=${LOAD}s soul_kv=$WR"; [ $OK -eq 1 ]
