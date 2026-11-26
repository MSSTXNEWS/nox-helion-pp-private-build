echo "C300: srv_k125"
cd /workspace/nox; date -u +%T
grep -v "Loading weights\|Writing model\|warn" ops/dpo/run5.log | grep -n "saved\|dst top5\|argmax\|5 шагов\|quant4\|gates\|Error\|Traceback\|rc=\|УДАЛЕНО\|df:" | cut -c1-200 | tail -14
ls -la models/student/Qwen3.6-35B-A3B-bnb4 | head; du -sh models/student/Qwen3.6-35B-A3B-bnb4; cat models/student/Qwen3.6-35B-A3B-bnb4/bnb4_check.json 2>&1 | cut -c1-300
pgrep -fa "quant4|gates_only|after_dump|chain5" | cut -c1-90; df -h /workspace | tail -1; ls STOP 2>&1
