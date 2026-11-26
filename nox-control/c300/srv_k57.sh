echo "C300: srv_k57"
cd /workspace/nox/ops/dpo
date -u +%T
grep -a "chain\|rc=\|Traceback\|Error\|ПРИНЯТ\|НЕ принят\|ворота" run.log | grep -v "pytree\|Tokeniz\|Dropping" | tail -n 25 | cut -c1-300
echo == report; cat dpo_report.json 2>&1 | head -30
echo == gates; ls -la gates_*.json 2>&1
ls /workspace/nox/STOP 2>&1 | head -1
echo == bench; cat /workspace/nox/ops/draw/bench_sd.txt 2>&1
ls -td /workspace/nox/distill_v2/ckpt_keep/cand_dpo_* 2>/dev/null | head -2
tail -n 4 /workspace/nox/agent/out/autotrain.log | cut -c1-250
pgrep -fa "distill_v2.py|gates_only|train_dpo" | cut -c1-90 | head
