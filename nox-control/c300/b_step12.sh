#!/bin/bash
# b_step12.sh: 1) перезапуск tts2 (патч ударений) + синтез T7 в wav; 2) маршруты sun_adapter :8097 и :8500, прокси /img в web_server.py
set -u
W=/workspace/nox
OUT=$W/web/site/qa/voice2; mkdir -p "$OUT"
echo "== 1) restart tts2"
pkill -f "tts2_server.py" 2>/dev/null; sleep 3
cd $W/c300_voice/voice2 && NOX_VOICE_MODELS=$W/voice_models nohup setsid nice -n 5 $W/voice2_venv/bin/python tts2_server.py >$W/svc/logs/tts2.log 2>&1 &
for i in $(seq 1 40); do curl -s --max-time 3 http://127.0.0.1:8095/health | grep -q '"ok": true' && break; sleep 4; done
curl -s --max-time 5 http://127.0.0.1:8095/health; echo
echo "== T7 synth"
T7='В XX веке музыка изменилась. Что дальше? Не знаю!'
for path in /synth /api/synth; do
  code=$(curl -s -o $OUT/t7_after_restart.wav -w "%{http_code}" --max-time 200 -X POST http://127.0.0.1:8095$path -H 'Content-Type: application/json' -d "{\"text\": \"$T7\", \"voice\": \"aidar\", \"format\": \"wav\"}")
  echo "$path -> $code"; [ "$code" = "200" ] && break
done
ls -la $OUT/t7_after_restart.wav 2>/dev/null
echo "== 2) sun_adapter / imgsvc"
for p in 8097 8500; do echo "-- :$p"; curl -s --max-time 5 http://127.0.0.1:$p/ | head -c 300; echo; curl -s --max-time 5 http://127.0.0.1:$p/health | head -c 300; echo; done
echo "-- routes in brain_img.py"
grep -n "path\|/img\|/draw\|post(" $W/brain/DEPLOY/staged/nox-control/wow7/img/brain_img.py | head -20
echo "-- /img proxy in web_server.py"
grep -n "img" $W/web/pkg/server/web_server.py | head -20
echo "-- studio/photo img calls"
grep -n "img/\|generate" $W/web/site/studio.html $W/web/site/photo.html | head -10
