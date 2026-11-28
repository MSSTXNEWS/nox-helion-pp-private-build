echo "K1: v8_dbg"
N=/workspace/nox; PY=$N/voice/venv/bin/python
curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/v8_bench.py?x=$RANDOM" -o /tmp/v8_bench.py
PORT=18797 $PY /tmp/v8_bench.py 2>&1 | grep -v "^{" | tail -25
curl -s -m20 -X POST 127.0.0.1:18797/tts -d '{"text":"Привет, как дела, расскажи коротко, что нового."}' -o /tmp/v8_q.wav
curl -s -m60 -N -X POST "127.0.0.1:18797/voice/turn?cid=v8dbg$RANDOM&user=owner" -H "Content-Type: audio/wav" --data-binary @/tmp/v8_q.wav 2>&1 | cut -c1-200 | head -12
ls /var/log/supervisor/ 2>/dev/null | grep -i voice; tail -n 15 /var/log/supervisor/nox_voice*err* 2>/dev/null | cut -c1-200
supervisorctl status nox_voice
