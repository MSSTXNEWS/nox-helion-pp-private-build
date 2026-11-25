#!/bin/bash
N=/workspace/nox
echo "== selfheal core"; grep -n -E "def |ORCH|owner|restart|spawn|Popen|start_cmd" $N/agent/nox_ops/svc_selfheal.py | cut -c1-190 | head -50
echo "== selfheal 1-40"; sed -n 1,40p $N/agent/nox_ops/svc_selfheal.py | cut -c1-200
echo "== nox_orch 8106/gptoss"; grep -n -i -E "8106|gpt-oss|gptoss|ensure|start_srv|llama-server" $N/stewards/nox_orch.py | cut -c1-200 | head -30
echo "== who runs 8106 cmd origin"; grep -rn -E "port 8106|--port.*8106|gpt-oss-20b-Q4_K_M" $N/stewards $N/agent/nox_ops $N/ops/*.sh $N/serve/*.sh 2>/dev/null | cut -c1-220 | head
echo "== judge_service REG/models"; sed -n 20,118p $N/judges/judge_service.py | cut -c1-170
echo "== judge_service env/limits & lazy flags"; grep -n -E "environ|\.off|\.flag|LAZY|lazy|unload|HOTSWAP|hotswap" $N/judges/judge_service.py | cut -c1-170 | head -20
echo "== judge loaded sizes"; curl -s -m5 127.0.0.1:8300/health | head -c 300; echo; curl -s -m5 127.0.0.1:8300/models 2>/dev/null | head -c 1500
