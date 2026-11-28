echo "K1: v8_stt_peek"
F=/workspace/nox/c300_voice/voice/stt_server.py
sed -n 170,330p $F | cut -c1-220
