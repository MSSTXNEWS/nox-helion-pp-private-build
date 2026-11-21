#!/usr/bin/env bash
# NOX voice: установка зависимостей. Идемпотентно (повторный запуск ничего не ломает), каждый пакет независимо,
# в конце печатает что поставилось / не поставилось. Серверы voice работают и без части пакетов (/health покажет).
#
# env: NOX_VOICE_VENV      venv (по умолчанию $HOME/.nox-voice-venv; --system-site-packages)
#      NOX_VOICE_TORCH_INDEX  индекс для CPU-torch (по умолчанию https://download.pytorch.org/whl/cpu; "pypi" = обычный PyPI)
#      NOX_VOICE_SKIP_TTS=1    не ставить coqui-tts/torch (тяжёлый XTTS) - останется Piper
#      NOX_VOICE_PIPER_VOICES  голоса Piper через пробел (по умолчанию "ru_RU-irina-medium es_ES-davefx-medium"; "" = не качать)
#      NOX_VOICE_MODELS        куда качать модели Piper (по умолчанию $HOME/nox-voice-models)
#      NOX_VOICE_PREFETCH=1    заранее скачать модель Whisper (NOX_STT_MODEL, по умолчанию small)
set -u
VENV="${NOX_VOICE_VENV:-$HOME/.nox-voice-venv}"
MODELS="${NOX_VOICE_MODELS:-$HOME/nox-voice-models}"
TORCH_INDEX="${NOX_VOICE_TORCH_INDEX:-https://download.pytorch.org/whl/cpu}"
PIPER_VOICES="${NOX_VOICE_PIPER_VOICES-ru_RU-irina-medium es_ES-davefx-medium}"
OK=(); FAIL=()

PY=python3
if [ ! -x "$VENV/bin/python" ]; then
  if "$PY" -m venv --system-site-packages "$VENV" 2>/dev/null; then echo "[venv] создан $VENV"; else
    echo "[venv] не удалось создать venv - ставлю в системный python (--user --break-system-packages)"; VENV=""; fi
fi
if [ -n "$VENV" ]; then PIP=("$VENV/bin/python" -m pip install -q); PYX="$VENV/bin/python"
else PIP=("$PY" -m pip install -q --user --break-system-packages); PYX="$PY"; fi
"$PYX" -m pip --version >/dev/null 2>&1 || { echo "pip недоступен для $PYX"; exit 1; }

# имя pip-пакета -> имя python-модуля для проверки
try_pkg() {  # try_pkg <pip-spec> <module> [extra pip args...]
  local spec="$1" mod="$2"; shift 2
  if "$PYX" -c "import $mod" >/dev/null 2>&1; then OK+=("$spec (уже есть)"); return; fi
  if "${PIP[@]}" "$@" "$spec" >/tmp/nox_voice_pip.$$ 2>&1 && "$PYX" -c "import $mod" >/dev/null 2>&1; then OK+=("$spec")
  else FAIL+=("$spec: $(tail -n 2 /tmp/nox_voice_pip.$$ | tr '\n' ' ' | cut -c1-200)"); fi
  rm -f /tmp/nox_voice_pip.$$
}

try_pkg numpy numpy
try_pkg onnxruntime onnxruntime
try_pkg ctranslate2 ctranslate2
try_pkg faster-whisper faster_whisper
try_pkg piper-tts piper
if [ "${NOX_VOICE_SKIP_TTS:-0}" != "1" ]; then
  # Оригинальный пакет TTS (coqui) не ставится на Python 3.12; поддерживаемый форк - coqui-tts (модуль TTS).
  if ! "$PYX" -c "import torch" >/dev/null 2>&1; then
    if [ "$TORCH_INDEX" = "pypi" ]; then try_pkg torch torch; else
      try_pkg torch torch --index-url "$TORCH_INDEX"
      "$PYX" -c "import torch" >/dev/null 2>&1 || try_pkg torch torch; fi
  else OK+=("torch (уже есть)"); fi
  try_pkg coqui-tts TTS
fi

# голоса Piper
if [ -n "$PIPER_VOICES" ] && "$PYX" -c "import piper" >/dev/null 2>&1; then
  mkdir -p "$MODELS"
  for v in $PIPER_VOICES; do
    if [ -f "$MODELS/$v.onnx" ]; then OK+=("piper voice $v (уже есть)"); continue; fi
    if (cd "$MODELS" && "$PYX" -m piper.download_voices "$v" >/tmp/nox_voice_pv.$$ 2>&1) && [ -f "$MODELS/$v.onnx" ]; then OK+=("piper voice $v")
    else FAIL+=("piper voice $v: $(tail -n 1 /tmp/nox_voice_pv.$$ | cut -c1-160)"); fi
    rm -f /tmp/nox_voice_pv.$$
  done
fi

# предзагрузка Whisper
if [ "${NOX_VOICE_PREFETCH:-0}" = "1" ] && "$PYX" -c "import faster_whisper" >/dev/null 2>&1; then
  M="${NOX_STT_MODEL:-small}"
  if "$PYX" -c "from faster_whisper import WhisperModel; WhisperModel('$M', device='cpu', compute_type='int8')" >/tmp/nox_voice_wm.$$ 2>&1; then OK+=("whisper model $M")
  else FAIL+=("whisper model $M: $(tail -n 1 /tmp/nox_voice_wm.$$ | cut -c1-160)"); fi
  rm -f /tmp/nox_voice_wm.$$
fi

echo; echo "===== ПОСТАВИЛОСЬ ====="; for x in "${OK[@]:-}"; do [ -n "$x" ] && echo "  + $x"; done
echo "===== НЕ ПОСТАВИЛОСЬ ====="; for x in "${FAIL[@]:-}"; do [ -n "$x" ] && echo "  - $x"; done
echo "===== СИСТЕМНОЕ ====="
command -v ffmpeg >/dev/null && echo "  + ffmpeg (webm/opus на входе STT)" || echo "  - ffmpeg нет (apt install ffmpeg): STT примет только WAV/PCM16"
command -v arecord >/dev/null && echo "  + arecord (микрофон)" || echo "  - arecord нет: голосовой цикл на сервере используйте с --input file:/stdin"
if [ -n "$VENV" ]; then echo "venv python: $VENV/bin/python"; fi
echo "Piper-голоса в: $MODELS (задайте NOX_PIPER_MODEL_RU / _ES на .onnx)"
echo "Smart Turn ONNX (опционально): положите модель и задайте NOX_SMART_TURN_MODEL; без неё работает эвристика."
[ "${#FAIL[@]}" -eq 0 ] && exit 0 || exit 3
