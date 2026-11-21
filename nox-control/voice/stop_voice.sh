#!/usr/bin/env bash
# Остановка STT/TTS, запущенных start_voice.sh (только свои pid-файлы, чужие процессы не трогает).
RUN="${NOX_VOICE_RUNDIR:-$HOME/.nox-voice-run}"
for n in stt tts; do
  f="$RUN/$n.pid"
  if [ -f "$f" ] && kill -0 "$(cat "$f")" 2>/dev/null; then kill "$(cat "$f")" && echo "[$n] остановлен"; else echo "[$n] не запущен"; fi
  rm -f "$f"
done
