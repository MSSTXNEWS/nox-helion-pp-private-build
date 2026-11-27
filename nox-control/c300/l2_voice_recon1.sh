echo "K1: l2_voice_recon1"
N=/workspace/nox
ls $N/voice_models $N/voice_models/* | head -40
ps aux | grep -i -E "whisper|tts|silero|voice|stt" | grep -v grep | cut -c1-220 | head
ss -ltnp | grep -E "python" | awk '{print $4}' | tr '\n' ' '; echo
ls $N/svc; ls $N/svc/whisperlive | head; tail -n 5 $N/svc/logs/whisperlive.log | cut -c1-200
grep -rn -i -E "stt|/api/voice|transcribe|tts" $N/web/pkg/server/*.py 2>/dev/null | cut -c1-160 | head -15
$N/venv/bin/pip list 2>/dev/null | grep -i -E "faster|ctranslate|whisper|silero|pipecat|onnx|soundfile|torchaudio|librosa|runorm|ru_norm|aiohttp|websockets|silero"
ls $N/models/warm | head -30; ls $N/models | head -30
ls /workspace/.hf_home/hub | grep -i -E "whisper|t-one|silero|tone" 
df -h /workspace | tail -1
