echo "K1: ln_t3"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
echo "== STT debug"
curl -s -m20 -X POST 127.0.0.1:8094/synth -H 'Content-Type: application/json' -d '{"text":"В тысяча девятьсот девяносто шестом году я заплатил двадцать пять рублей.","lang":"ru","format":"wav"}' -o /tmp/ln_tts2.wav
python3 - <<'PY'
import wave
w=wave.open('/tmp/ln_tts2.wav'); print('wav',w.getframerate(),w.getnchannels(),w.getnframes())
PY
xxd /tmp/ln_tts2.wav | head -3
for q in "language=ru" "language=ru&format=wav"; do curl -s -m60 -X POST "127.0.0.1:8093/transcribe?$q" -H 'Content-Type: audio/wav' --data-binary @/tmp/ln_tts2.wav | head -c 700; echo; done
echo "== searx"
curl -s -m15 "127.0.0.1:8888/search?q=python&format=json" | python3 -c "
import sys,json;d=json.load(sys.stdin);print('n',len(d['results']),'unresp',d.get('unresponsive_engines'))" 2>&1 | head -3
curl -s -m20 -X POST 127.0.0.1:8130/v1/tools/call -H 'Content-Type: application/json' -d '{"name":"web_search","arguments":{"query":"погода в Москве"}}' | head -c 300; echo
tail -5 $N/tools/searxng/*.log $N/agent/out/*searx* 2>/dev/null | cut -c1-200 | head -10
grep -E "engines|disabled|outgoing|proxies" -A3 $N/tools/searxng/searxng-src/searx/settings.yml 2>/dev/null | head -3
ls $N/tools/searxng | head; grep -n "SEARXNG_SETTINGS\|environment" /etc/supervisor/conf.d/nox_searxng.conf | cut -c1-160
