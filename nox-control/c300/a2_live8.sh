echo "C300: a2_live8"
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/b52a7e2f1123acaab09cb23d35ea18321d9d3705/nox-control/c300; A=/workspace/nox/agents
for f in a2_eval_llm.py a2_live6.py; do curl -fsSL "$R/$f" -o $A/$f; done
echo "== measure"; cat $A/measure_before.log $A/measure_after.log $A/measure_after2.log 2>&1 | cut -c1-420
pgrep -fc 'python nox_agents.py'; curl -s -m5 127.0.0.1:8810/health | head -c 90; echo
setsid -f sh -c "$A/venv/bin/python $A/a2_live6.py > $A/live6b.log 2>&1" </dev/null >/dev/null 2>&1
echo started
