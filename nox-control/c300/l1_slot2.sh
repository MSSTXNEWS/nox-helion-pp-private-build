echo "K1: l1_slot2"
cd /workspace/nox
grep -n "DONOR_URL\|chat/completions" agent/nox_agents/lib.py | cut -c1-200 | head -12
grep -n "BODY\|chat/completions\|json.dumps" ops/sun_adapter/sun_adapter.py | cut -c1-200 | head -25
grep -rn "chat/completions" agent/nox_agents/*.py agent/nox_agents/mind/*.py 2>/dev/null | grep -v lib.py | cut -c1-190 | head -12
