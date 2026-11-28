echo "K1: v8_recon2"
N=/workspace/nox
sha256sum $N/mods/voice_service.py $N/mods/piper_tts.py | cut -c1-16,65-; ls -la $N/mods/voice_service.py* | head
ls -la $N/voice_models/silero | head; du -sh $N/voice_models/* 2>/dev/null | head
for py in $N/voice/venv/bin/python $N/voice_venv/bin/python $N/voice2_venv/bin/python $N/venv/bin/python python3; do echo "== $py"; $py -c "
import importlib
for m in ('piper','onnxruntime','numpy','torch','silero_vad','tone','pipecat','sounddevice','soundfile'):
    try:
        x=importlib.import_module(m);print(m,getattr(x,'__version__','ok'))
    except Exception as e: print(m,'NO')
" 2>&1 | tr '\n' ' '; echo; done
$N/voice/venv/bin/pip list 2>/dev/null | grep -i -E "piper|onnx|numpy"
ps -o args= -p $(pgrep -f mods/voice_service.py | head -1); tr '\0' '\n' < /proc/$(pgrep -f mods/voice_service.py | head -1)/environ | grep -E "^NOX_" | sed 's/=.*//' | tr '\n' ' '
echo; grep -rn "voice_service" $N/ops/*.sh $N/*.sh /etc/supervisor/conf.d/*.conf 2>/dev/null | cut -c1-220 | head -5
grep -n "def \|route\|POST\|GET" $N/c300_voice/voice/stt_server.py | head -30
$N/venv/bin/python - <<'P' 2>&1 | tail -3
import glob,json
for f in glob.glob('/workspace/nox/**/self_now*',recursive=True)[:5]: print(f)
P
find $N -maxdepth 3 -name "self_now*" 2>/dev/null | head -3
echo "== baseline TTS /tts (10x, short sentence)"
for i in 1 2 3 4 5 6 7 8 9 10; do /usr/bin/time -f "%e" curl -s -m30 -o /dev/null -X POST 127.0.0.1:18797/tts -d '{"text":"Понял, слушаю."}' 2>&1 | tr '\n' ' '; done; echo
echo "== baseline TTS longer"
for i in 1 2 3; do /usr/bin/time -f "%e" curl -s -m30 -o /dev/null -X POST 127.0.0.1:18797/tts -d '{"text":"Сейчас посмотрю, что у нас с сервером, и расскажу коротко."}' 2>&1 | tr '\n' ' '; done; echo
echo "== t-one size"; curl -s -m15 https://huggingface.co/api/models/t-tech/T-one | head -c 900; echo
echo "== qwen3tts"; curl -s -m15 "https://huggingface.co/api/models?search=Qwen3-TTS&limit=8" | head -c 800; echo
echo "== pip dl probes"; pip download --no-deps -d /tmp/pp pipecat-ai==0.0.1 2>&1 | tail -1
