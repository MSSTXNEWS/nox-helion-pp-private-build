echo "K1: ln_r9"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
GD=$(readlink -f /proc/$(ss -ltnp | grep ':18218 ' | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)/cwd); echo $GD; ls $GD | head
sed -n 1,45p $GD/guard_svc.py | cut -c1-190
echo "== agents"; sed -n 662,668p $N/agents/nox_agents.py | cut -c1-200; sed -n 717,733p $N/agents/nox_agents.py | cut -c1-200
echo "== tts synth"; sed -n 440,457p $N/c300_voice/voice/tts_server.py | cut -c1-200
grep -n "_transcribe" $N/c300_voice/voice/stt_server.py | head -2
