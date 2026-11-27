echo "K1: ln_r8"
export RUNNER_TRACKING_ID=""
N=/workspace/nox
sed -n 1,40p $N/svc/guard_svc.py | cut -c1-200
echo "== tts"; grep -nE "path (==|in)|startswith|X-|Content-Type|\.wav|numbers|num2|spell" $N/c300_voice/voice/tts_server.py | sed -n 1,25p | cut -c1-170
sed -n 355,372p $N/c300_voice/voice/stt_server.py | cut -c1-170
echo "== agents"; grep -nE "/task|/consilium|/worms|/board|/golden|/dispatch|/restart" $N/agents/nox_agents.py | head -30 | cut -c1-170
echo "== tools gw"; grep -nE "\"/[a-z_/]+\"|PORT" $N/tools/tools_gateway.py | head -14 | cut -c1-140
grep -nE "port:|bind" $N/tools/searxng/settings.yml 2>/dev/null | head -3
