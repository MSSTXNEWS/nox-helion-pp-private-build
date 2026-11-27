echo "K1: l2_stt_recon2"
V=/workspace/nox/c300_voice/voice
grep -n -E "env(_int|_bool|_float)?\(\"NOX_STT|WhisperModel|compute_type|device" $V/stt_server.py $V/common.py | cut -c1-220 | head -30
cat $V/start_voice.sh | cut -c1-200 | head -40
tr '\0' '\n' < /proc/2528/environ | grep -E "^NOX_(STT|TTS|VOICE)" ; ls /workspace/nox/voice_venv/lib/python3*/site-packages/nvidia 2>/dev/null | head
