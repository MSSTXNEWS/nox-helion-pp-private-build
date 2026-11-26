echo "C300: NAME"
sleep 240; date -u +%T
grep -a "chain2\|rc=\|Traceback\|Error\|ПРИНЯТ\|gates\|train" /workspace/nox/ops/dpo/run.log | grep -v "pytree\|Tokeniz\|Dropping" | tail -n 8 | cut -c1-260
tail -c 600 /workspace/nox/ops/dpo/run.log | tr '\r' '\n' | tail -n 2 | cut -c1-200
ls /workspace/nox/STOP 2>&1 | head -1
