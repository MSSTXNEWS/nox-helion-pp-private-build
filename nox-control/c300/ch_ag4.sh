echo "C300: ch_ag4"
cb=$(date +%s); R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_ui1; A=/workspace/nox/agent/nox_agents
mkdir -p /tmp/cha; for f in ch_golden_agent.py ch_golden_run.py patch_sup.py; do curl -fsSL --retry 5 --retry-all-errors "$R/$f?cb=$cb" -o /tmp/cha/$f || { echo FAIL $f; exit 0; }; done
grep -q "MAXAGE" /tmp/cha/ch_golden_agent.py || { echo STALE; exit 0; }
cp $A/supervisor.py $A/supervisor.py.bak_ch_$cb
cp /tmp/cha/ch_golden_agent.py $A/ch_golden_agent.py; cp /tmp/cha/ch_golden_run.py $A/ch_golden_run.py
python3 /tmp/cha/patch_sup.py && python3 -m py_compile $A/supervisor.py $A/ch_golden_agent.py && echo compiled || { cp $A/supervisor.py.bak_ch_$cb $A/supervisor.py; echo rollback; }
grep -n "ch-golden" $A/supervisor.py | cut -c1-150
cd /workspace/nox/agent && /workspace/nox/agents/venv/bin/python -c "
import sys; sys.path.insert(0,'/workspace/nox/agent')
from nox_agents import ch_golden_agent as m; print(m.tick())" 2>&1 | tail -3
