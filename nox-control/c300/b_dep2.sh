V=/workspace/nox/voice2_venv
$V/bin/pip install -q scipy 2>&1 | tail -2
pkill -f voice2/tts2_server.py; pkill -f "tts2_server.py"; pkill -f test10.py; sleep 1
cd /workspace/nox/c300_voice/voice2; export NOX_VOICE_MODELS=/workspace/nox/voice_models
nohup setsid nice -n 5 $V/bin/python tts2_server.py > /workspace/nox/svc/logs/tts2.log 2>&1 &
sleep 25
nohup setsid $V/bin/python test10.py > /workspace/nox/svc/logs/tts2_test.log 2>&1 &
sleep 120
tail -c 3500 /workspace/nox/svc/logs/tts2_test.log; tail -5 /workspace/nox/svc/logs/tts2.log | cut -c1-300
