#!/bin/bash
S=/workspace/nox/web/site; X=$S/vendor/nox-x
ls -la $X/excalidraw | head -20; ls $X/react | head; cat $X/excalidraw/VERSION 2>/dev/null
ls $S/vendor | grep -i excal; ls $S/vendor/excalidraw-excalidraw 2>/dev/null | head
echo ==board; wc -c $S/board.html; sed -n '/<body/,$p' $S/board.html | grep -v 'src="./nox-' | cut -c1-240 | head -25
grep -o '<script[^>]*src="[^"]*"' $S/board.html | grep -iv "nox-nav\|dock\|ninja\|minichat\|pwa\|pult\|sun\|state\|cmd\|actions\|cast\|radial\|live\|gesture\|worlds\|theme\|fx" | head
curl -s -m60 -X POST http://127.0.0.1:8091/svc/tts2/synth -H 'Content-Type: application/json' -d '{"text":"В 1996 году сводка новостей: главное за сегодня.","voice":"aidar","normalize":true,"accent":true,"pauses":true,"format":"wav"}' -o /tmp/s2_syn.wav -w "http=%{http_code} size=%{size_download} ct=%{content_type}\n"
python3 - <<'PY'
import wave,audioop
try:
    w=wave.open('/tmp/s2_syn.wav');d=w.readframes(w.getnframes());print('wav',w.getnchannels(),w.getframerate(),round(w.getnframes()/w.getframerate(),2),'sec rms',audioop.rms(d,w.getsampwidth()))
except Exception as e: print('ERR',e)
PY
