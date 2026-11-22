#!/bin/bash
ask(){ S=$(date +%s.%N); curl -s -N -m 150 http://127.0.0.1:8091/api/chat -d "{\"model\":\"nox-helion:latest\",\"messages\":[{\"role\":\"user\",\"content\":\"$1\"}]}" > /tmp/e2e.out; E=$(date +%s.%N)
python3 - "$S" "$E" <<'PY'
import sys,json
t="";n=0
for l in open('/tmp/e2e.out'):
    try:j=json.loads(l)
    except: continue
    t+=j.get('message',{}).get('content','');n+=1
print("t=%.1fs frames=%d"%(float(sys.argv[2])-float(sys.argv[1]),n)); print(t[:600])
PY
}
echo "### Q1"; ask "Привет. Кто ты и на чём работаешь?"
echo "### Q2"; ask "Объясни по-русски в трёх предложениях, что такое оперативная память."
echo "### Q3 память"; ask "Что ты помнишь обо мне?"
echo "### TTS RU"; curl -s -m 60 -o /tmp/r.wav -w "bytes=%{size_download}\n" -X POST http://127.0.0.1:8091/tts/synth -H 'Content-Type: application/json' -d '{"text":"Оперативная память хранит данные, с которыми работает процессор.","lang":"auto","format":"wav"}'
python3 -c "
import wave;w=wave.open('/tmp/r.wav');print('dur=%.1fs rate=%d'%(w.getnframes()/w.getframerate(),w.getframerate()))"
grep -E "def detect_lang" -A12 /root/nox/repo/nox-control/voice/tts_server.py | head -16
