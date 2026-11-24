V=/workspace/nox/c300_voice/voice
echo "== tts_server"; cat $V/tts_server.py | cut -c1-200 | head -150
echo "== textproc"; cat $V/textproc.py | cut -c1-200 | head -80
echo "== pip"; /workspace/nox/voice_venv/bin/pip list 2>/dev/null | head -60
echo "== models"; ls -la /workspace/nox/voice_models; /workspace/nox/voice_venv/bin/python -V
df -h /workspace | tail -1
