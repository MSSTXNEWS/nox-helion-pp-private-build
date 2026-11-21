#!/usr/bin/env bash
# Запуск STT (8093) и TTS (8094) через nohup. Идемпотентно: уже работающий сервис не перезапускается.
# 8091 занят nox-bridge, 8080-8083/8098 - другими сервисами; порты тут отличаются намеренно.
# Использование: start_voice.sh [stt|tts|all]   env: NOX_STT_PORT, NOX_TTS_PORT, NOX_VOICE_VENV, NOX_VOICE_LOGDIR, + env сервисов (см. README)
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
VENV="${NOX_VOICE_VENV:-$HOME/.nox-voice-venv}"
PY=python3; [ -x "$VENV/bin/python" ] && PY="$VENV/bin/python" && export PATH="$VENV/bin:$PATH"
LOG="${NOX_VOICE_LOGDIR:-$HOME/nox-voice-logs}"; RUN="${NOX_VOICE_RUNDIR:-$HOME/.nox-voice-run}"
mkdir -p "$LOG" "$RUN"
STT_PORT="${NOX_STT_PORT:-8093}"; TTS_PORT="${NOX_TTS_PORT:-8094}"
export NOX_STT_PORT="$STT_PORT" NOX_TTS_PORT="$TTS_PORT"
# модели Piper по умолчанию из каталога install_deps.sh
MODELS="${NOX_VOICE_MODELS:-$HOME/nox-voice-models}"
[ -z "${NOX_PIPER_MODEL_RU:-}" ] && [ -f "$MODELS/ru_RU-irina-medium.onnx" ] && export NOX_PIPER_MODEL_RU="$MODELS/ru_RU-irina-medium.onnx"
[ -z "${NOX_PIPER_MODEL_ES:-}" ] && [ -f "$MODELS/es_ES-davefx-medium.onnx" ] && export NOX_PIPER_MODEL_ES="$MODELS/es_ES-davefx-medium.onnx"

port_busy() { "$PY" - "$1" <<'PYEOF'
import socket, sys
s = socket.socket(); s.settimeout(0.5)
sys.exit(0 if s.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)
PYEOF
}
start() {  # start <name> <port> <module>
  local name="$1" port="$2" mod="$3" pidf="$RUN/$1.pid"
  if [ -f "$pidf" ] && kill -0 "$(cat "$pidf")" 2>/dev/null; then echo "[$name] уже запущен (pid $(cat "$pidf"), порт $port)"; return 0; fi
  if port_busy "$port"; then echo "[$name] ОШИБКА: порт $port занят другим процессом - задайте NOX_${name^^}_PORT"; return 1; fi
  nohup "$PY" "$HERE/$mod" >>"$LOG/$name.log" 2>&1 &
  echo $! >"$pidf"; disown 2>/dev/null || true
  for _ in $(seq 1 30); do
    sleep 0.5
    if curl -fsS -m2 "http://127.0.0.1:$port/health" >/dev/null 2>&1; then echo "[$name] запущен: порт $port, лог $LOG/$name.log"; return 0; fi
    kill -0 "$(cat "$pidf")" 2>/dev/null || { echo "[$name] упал при старте, см. $LOG/$name.log"; tail -n 5 "$LOG/$name.log"; return 1; }
  done
  echo "[$name] не ответил на /health за 15 с (процесс жив, возможно грузит модель), см. $LOG/$name.log"; return 0
}
rc=0
case "${1:-all}" in
  stt) start stt "$STT_PORT" stt_server.py || rc=1 ;;
  tts) start tts "$TTS_PORT" tts_server.py || rc=1 ;;
  all) start stt "$STT_PORT" stt_server.py || rc=1; start tts "$TTS_PORT" tts_server.py || rc=1 ;;
  *) echo "usage: $0 [stt|tts|all]"; exit 2 ;;
esac
for p in "$STT_PORT" "$TTS_PORT"; do curl -fsS -m3 "http://127.0.0.1:$p/health" 2>/dev/null | head -c 400; echo; done
exit $rc
