echo S4RUN:s4_mem5
D=/root/nox/memory/s03.db; [ -f $D ] || D=$(ls /workspace/nox/memory/s03.db /workspace/nox/state/memory/s03.db 2>/dev/null | head -1); echo DB=$D; ls -la $D
NC=/workspace/nox/brain/DEPLOY/staged/nox-control; ls $NC | head -5
PY=/workspace/nox/venv/bin/python; [ -x $PY ] || PY=python3
[ -n "$D" ] && [ -f "$D" ] || { echo NO_DB; exit 0; }
cd $NC && NOX_MEMORY_DB=$D NOX_RECALL_PORT=8189 NOX_WOW7_MEM=/workspace/nox/wow7/mem nohup $PY -m qs6.recall_server > /workspace/nox/agent/out/recall_s4.log 2>&1 &
sleep 6; cat /workspace/nox/agent/out/recall_s4.log | tail -5
for b in '{"op":"health"}' '{"op":"search","query":"проект","k":3}' '{"op":"journal","limit":3}' '{"op":"core","budget_tokens":200}'; do echo "-- $b"; curl -s -m8 -X POST -H 'Content-Type: application/json' -d "$b" 127.0.0.1:8189/api | head -c 300; echo; done
curl -s -m4 127.0.0.1:8189/health | head -c 200
