echo "K1: v8_recon"
N=/workspace/nox
ps aux | grep -i -E "nox_voice|nox_stt|voice|piper|gigaam|tts" | grep -v grep | cut -c1-200 | head
ss -ltnp | grep -E "18797|8400|8093" | awk '{print $4,$6}'
ls -la $N/voice $N/c300_voice 2>/dev/null | head -40
ls $N/c300_voice/* | head -40
for p in 18797 8400; do echo "health $p: $(curl -s -m3 127.0.0.1:$p/health | cut -c1-300)"; done
systemctl list-units 2>/dev/null | grep -i -E "voice|stt" | head; ls /etc/supervisor/conf.d 2>/dev/null | head
grep -rl "nox_voice\|nox_stt" $N/*.sh $N/ops/*.sh $N/svc 2>/dev/null | head
$N/venv/bin/pip list 2>/dev/null | grep -i -E "piper|onnx|silero|pipecat|torch|numpy|gigaam|tone|webrtc|sherpa|vosk" 
python3 -c "import onnxruntime,sys;print('ort',onnxruntime.__version__)" 2>&1 | tail -1
nproc; free -g | head -2; df -h /workspace | tail -1; uptime
ls $N/models | grep -i -E "silero|tone|qwen3.?tts|giga" ; find $N -maxdepth 4 -iname "*silero*" -o -maxdepth 4 -iname "*qwen3*tts*" 2>/dev/null | head
