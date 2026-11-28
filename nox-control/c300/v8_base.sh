echo "K1: v8_base"
N=/workspace/nox
python3 -I $(dirname $0)/v8_bench.py 2>&1 | tail -3 || true
B=$(find / -maxdepth 6 -name v8_bench.py -path "*c300*" 2>/dev/null | head -1); echo "bench=$B"
[ -n "$B" ] && python3 -I $B 2>&1 | tail -3
echo "== pad"; python3 -c "
import json;j=json.load(open('$N/state/core/self_now.json'));print(list(j.keys())[:40]);print(json.dumps(j.get('pad'))[:300])"
echo "== T-one tree"; curl -s -m20 "https://huggingface.co/api/models/t-tech/T-one/tree/main?recursive=1" | python3 -c "
import sys,json
for f in json.load(sys.stdin): print(f.get('path'),f.get('size'))" 2>&1 | head -30
echo "== qwen3tts sizes"; for m in Qwen/Qwen3-TTS-12Hz-0.6B-Base Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice; do curl -s -m20 "https://huggingface.co/api/models/$m/tree/main?recursive=1" | python3 -c "
import sys,json
t=0
for f in json.load(sys.stdin): t+=f.get('size') or 0
print('$m',round(t/1e6),'MB')" 2>&1|tail -1; done
echo "== silero pip"; $N/voice/venv/bin/pip download --no-deps -d /tmp/v8sv silero-vad 2>&1 | tail -2; ls -la /tmp/v8sv 2>/dev/null
echo "== piper api"; $N/voice/venv/bin/python -c "
import piper,inspect;from piper import PiperVoice
print(piper.__file__);print(inspect.signature(PiperVoice.synthesize_stream_raw))"
