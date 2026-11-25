echo S4RUN:s4_mem7
D=/workspace/nox/state/memory/nox_memory.sqlite; cp -n $D $D.bak_s4_1 && echo backup ok
NC=/workspace/nox/brain/DEPLOY/staged/nox-control; PY=/workspace/nox/venv/bin/python
mkdir -p /workspace/nox/agent/out
cd $NC && NOX_MEMORY_DB=$D NOX_RECALL_PORT=8189 NOX_WOW7_MEM=/workspace/nox/wow7/mem nohup $PY -m qs6.recall_server > /workspace/nox/agent/out/recall_s4.log 2>&1 &
sleep 8; tail -5 /workspace/nox/agent/out/recall_s4.log
for b in '{"op":"health"}' '{"op":"search","query":"проект","k":3}' '{"op":"journal","limit":3}' '{"op":"core","budget_tokens":200}'; do echo "-- $b"; curl -s -m8 -X POST -H 'Content-Type: application/json' -d "$b" 127.0.0.1:8189/api | head -c 300; echo; done
curl -s -m4 127.0.0.1:8189/health | head -c 200
