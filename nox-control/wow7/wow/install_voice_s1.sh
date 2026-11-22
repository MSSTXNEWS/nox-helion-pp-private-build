#!/usr/bin/env bash
# WOW-02 · мужской голос RU/ES для NOX на S1 (CPU): Silero v5 (ru) + Kokoro (es) + запасной Piper + silero-vad.
# Надстройка над nox-control/voice/install_deps.sh (faster-whisper, piper, XTTS ставит он) - здесь только то, что нужно voice_server.py.
# Идемпотентно; каждый шаг независим; в конце печатает что поставилось/нет. Ничего не качает при --dry-run.
# Опции: --dry-run  --start (запустить voice_server:8095 и presence:8096, если порты свободны)  --prefetch (прогреть Kokoro)
#        --no-kokoro  --no-silero  --piper "ru_RU-dmitri-medium es_ES-davefx-medium"
# env: NOX_VOICE_VENV (~/.nox-voice-venv)  NOX_VOICE_MODELS (~/nox-voice-models)  NOX_CONTROL (/root/nox/src/nox-control)
#      NOX_RECEIPTS (/root/nox/receipts)  NOX_TORCH_INDEX (https://download.pytorch.org/whl/cpu)
# Лицензии: Silero v5_ru - CC BY-NC (личное/некоммерческое использование), Kokoro - Apache-2.0, Piper - MIT, silero-vad - MIT.
set -u
DRY=0; START=0; PREFETCH=0; KOKORO=1; SILERO=1
PIPER_VOICES="ru_RU-dmitri-medium es_ES-davefx-medium"
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1;; --start) START=1;; --prefetch) PREFETCH=1;; --no-kokoro) KOKORO=0;; --no-silero) SILERO=0;;
    --piper) shift; PIPER_VOICES="${1-}";;
    -h|--help) sed -n 2,10p "$0"; exit 0;;
    *) echo "неизвестная опция: $1" >&2; exit 2;;
  esac; shift
done
VENV="${NOX_VOICE_VENV:-$HOME/.nox-voice-venv}"
MODELS="${NOX_VOICE_MODELS:-$HOME/nox-voice-models}"
CONTROL="${NOX_CONTROL:-/root/nox/src/nox-control}"
RECEIPTS="${NOX_RECEIPTS:-/root/nox/receipts}"
TORCH_INDEX="${NOX_TORCH_INDEX:-https://download.pytorch.org/whl/cpu}"
SILERO_URL="https://models.silero.ai/models/tts/ru/v5_ru.pt"
PIPER_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main"
OK=(); FAIL=(); SKIP=()

run() { if [ "$DRY" = 1 ]; then echo "[dry-run] $*"; else "$@"; fi; }
log() { echo "[wow-02] $*"; }

PYX="$VENV/bin/python"
if [ ! -x "$PYX" ]; then
  if [ "$DRY" = 1 ]; then log "[dry-run] python3 -m venv --system-site-packages $VENV"; PYX=python3
  elif python3 -m venv --system-site-packages "$VENV" 2>/dev/null; then log "venv создан: $VENV"
  else log "venv не создался - используем системный python3"; PYX=python3; fi
fi
pipi() { run "$PYX" -m pip install -q "$@"; }
have() { [ "$DRY" = 1 ] && return 1; "$PYX" -c "import $1" >/dev/null 2>&1; }
step() {  # step <имя> <команда...>
  local n="$1"; shift
  if [ "$DRY" = 1 ]; then log "[dry-run] $n: $*"; SKIP+=("$n (dry-run)"); return; fi
  if "$@"; then OK+=("$n"); else FAIL+=("$n"); fi
}

# 1. torch (CPU) - нужен Silero и Kokoro
if [ "$SILERO" = 1 ] || [ "$KOKORO" = 1 ]; then
  if have torch; then OK+=("torch (уже есть)"); else step "torch" pipi torch --index-url "$TORCH_INDEX"; fi
fi
# 2. Silero v5 ru: файл модели (torch.package), проверка размера
if [ "$SILERO" = 1 ]; then
  F="$MODELS/silero/v5_ru.pt"
  if [ -s "$F" ]; then OK+=("silero v5_ru (уже есть)")
  else
    run mkdir -p "$MODELS/silero"
    step "silero v5_ru" bash -c "curl -fL --retry 3 --max-time 600 -o '$F.part' '$SILERO_URL' && [ \$(stat -c %s '$F.part') -gt 10000000 ] && mv '$F.part' '$F' || { rm -f '$F.part'; exit 1; }"
  fi
fi
# 3. Kokoro + espeak-ng (es: em_alex / em_santa)
if [ "$KOKORO" = 1 ]; then
  if command -v espeak-ng >/dev/null 2>&1; then OK+=("espeak-ng (уже есть)")
  elif command -v apt-get >/dev/null 2>&1 && [ "$(id -u)" = 0 ]; then step "espeak-ng" bash -c "apt-get install -y -q espeak-ng >/dev/null"
  else FAIL+=("espeak-ng (нужен root+apt: apt install espeak-ng)"); fi
  if have kokoro; then OK+=("kokoro (уже есть)"); else step "kokoro" pipi "kokoro>=0.9.4" soundfile; fi
  if [ "$PREFETCH" = 1 ]; then step "kokoro веса (es)" "$PYX" -c "from kokoro import KPipeline; KPipeline(lang_code='e')"; fi
fi
# 4. silero-vad (перебивание)
if have silero_vad; then OK+=("silero-vad (уже есть)"); else step "silero-vad" pipi silero-vad onnxruntime; fi
# 5. Piper: мужские запасные голоса (только .onnx + .json)
for V in $PIPER_VOICES; do
  L="${V%%_*}"; C="${V%%-*}"; REST="${V#*-}"; NAME="${REST%-*}"; Q="${REST##*-}"
  D="$MODELS/piper"; P="$PIPER_BASE/$L/$C/$NAME/$Q/$V"
  if [ -s "$D/$V.onnx" ] && [ -s "$D/$V.onnx.json" ]; then OK+=("piper $V (уже есть)"); continue; fi
  run mkdir -p "$D"
  step "piper $V" bash -c "curl -fL --retry 3 -o '$D/$V.onnx.part' '$P.onnx' && curl -fL --retry 3 -o '$D/$V.onnx.json' '$P.onnx.json' && mv '$D/$V.onnx.part' '$D/$V.onnx'"
done
if ! have piper && [ "$DRY" = 0 ] && ! command -v piper >/dev/null 2>&1; then step "piper-tts" pipi piper-tts; fi

# 6. env-файл с путями (читается start-скриптами и unit-ами)
ENVF="$(dirname "$RECEIPTS")/state/voice_wow.env"
RU_PIPER="$MODELS/piper/ru_RU-dmitri-medium.onnx"; ES_PIPER="$MODELS/piper/es_ES-davefx-medium.onnx"
if [ "$DRY" = 1 ]; then log "[dry-run] записал бы $ENVF"; else
  mkdir -p "$(dirname "$ENVF")" 2>/dev/null
  cat > "$ENVF" <<ENV 2>/dev/null || FAIL+=("env-файл $ENVF")
NOX_CONTROL=$CONTROL
NOX_VOICE_MODELS=$MODELS
NOX_SILERO_PATH=$MODELS/silero/v5_ru.pt
NOX_PIPER_MODEL_RU=$RU_PIPER
NOX_PIPER_MODEL_ES=$ES_PIPER
NOX_VOICE_RU=aidar
NOX_VOICE_ES=em_alex
NOX_VOICE_PORT=8095
ENV
fi

# 7. запуск (по желанию)
free_port() { ! (exec 3<>/dev/tcp/127.0.0.1/"$1") 2>/dev/null; }
start_one() {  # start_one <имя> <порт> <скрипт> [аргументы]
  local n="$1" port="$2" f="$3"; shift 3
  if [ "$DRY" = 1 ]; then log "[dry-run] запустил бы $n на :$port ($f)"; return; fi
  if [ ! -f "$f" ]; then FAIL+=("$n: нет $f"); return; fi
  if ! free_port "$port"; then FAIL+=("$n: порт $port занят (чужой процесс не трогаю)"); return; fi
  mkdir -p "$HOME/nox-voice-logs"
  ( set -a; . "$ENVF"; set +a; nohup "$PYX" "$f" "$@" >"$HOME/nox-voice-logs/$n.log" 2>&1 & echo $! >"$HOME/nox-voice-logs/$n.pid" )
  sleep 2; if curl -fs "http://127.0.0.1:$port/health" >/dev/null 2>&1 || curl -fs "http://127.0.0.1:$port/presence/state" >/dev/null 2>&1 || curl -fs "http://127.0.0.1:$port/state" >/dev/null 2>&1; then OK+=("$n запущен :$port"); else FAIL+=("$n не ответил на :$port (см. $HOME/nox-voice-logs/$n.log)"); fi
}
if [ "$START" = 1 ]; then
  W="$CONTROL/wow7/wow"
  start_one voice_server 8095 "$W/voice_server.py"
  start_one presence 8096 "$W/presence.py" serve --port 8096
fi

echo "---- итог ----"
for x in "${OK[@]:-}"; do [ -n "$x" ] && echo "поставилось: $x"; done
for x in "${SKIP[@]:-}"; do [ -n "$x" ] && echo "пропущено:   $x"; done
for x in "${FAIL[@]:-}"; do [ -n "$x" ] && echo "НЕ вышло:    $x"; done

# 8. квитанция
RC=0; [ "${#FAIL[@]}" -gt 0 ] && RC=3
if [ "$DRY" = 1 ]; then log "[dry-run] записал бы квитанцию $RECEIPTS/WOW-02.json"; exit 0; fi
mkdir -p "$RECEIPTS" 2>/dev/null
J() { printf '%s\n' "$@" | "$PYX" -c 'import sys,json;print(json.dumps([l.rstrip("\n") for l in sys.stdin if l.strip()],ensure_ascii=False))'; }
printf '{"id":"WOW-02","ts":"%s","ok":%s,"installed":%s,"failed":%s,"models":"%s"}\n' \
  "$(date -u +%FT%TZ)" "$([ $RC = 0 ] && echo true || echo false)" "$(J "${OK[@]:-}")" "$(J "${FAIL[@]:-}")" "$MODELS" > "$RECEIPTS/WOW-02.json" || log "квитанцию записать не удалось"
exit $RC
