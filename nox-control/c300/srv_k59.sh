echo "C300: srv_k59"
/workspace/nox/venv/bin/python -I /tmp/probe37.py 2>&1 | tail -6 || echo noprobe
ls -la /tmp/probe37.py | head -1
grep -c "" /workspace/nox/agent/autotrain/rounds/r036/train.log; grep -a "скорость\|пауз\|yield" /workspace/nox/agent/autotrain/rounds/r03[56]/train.log | tail -4 | cut -c1-200
grep -c "_lw" /workspace/nox/ops/liska_selfkd.py
