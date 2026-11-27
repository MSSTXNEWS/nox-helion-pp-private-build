echo "K1: l2_stt_recon1"
V=/workspace/nox/c300_voice/voice; ls $V; wc -l $V/stt_server.py
sed -n 1,70p $V/stt_server.py | cut -c1-200
supervisorctl status 2>&1 | grep -i -E "stt|voice|tts|whisper"
/workspace/nox/voice_venv/bin/pip list 2>/dev/null | grep -i -E "faster|ctranslate|onnx|torch|huggingface|numpy|pipecat|tone"
curl -s -m 5 127.0.0.1:8093/health | head -c 300; echo
curl -sI -m 8 https://huggingface.co/deepdml/faster-whisper-large-v3-turbo-ct2/resolve/main/config.json | head -3
