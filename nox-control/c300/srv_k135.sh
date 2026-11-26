echo "C300: srv_k135"
cd /workspace/nox; df -h /workspace|tail -1
echo "--- test_disk источники"; grep -rIn "test_disk\|bigfile" --include=*.py --include=*.sh . 2>/dev/null | grep -v "/venv\|\.bak\|site-packages" | cut -c1-200 | head -12
echo "--- pytest процессы/логи"; pgrep -fa "pytest|test_dsp" | grep -v pgrep | cut -c1-150 | head; ls -la --time-style=+%F_%T $(find . -maxdepth 3 -name "test_dsp*" -not -path "./venv*" 2>/dev/null | head -5) 2>/dev/null
grep -rIl "test_dsp\|pytest" /etc/supervisor/conf.d state/orch/*.log agent/out/*.log 2>/dev/null | head; crontab -l 2>/dev/null | grep -i "pytest\|test_\|qa_" | head -5
echo "--- autotrain"; ls -la state/core/disk_low.flag* 2>&1; cat state/core/disk_low.flag 2>/dev/null | head -3; cat state/tok_budget_max
tail -n 5 agent/autotrain/autotrain.log 2>/dev/null | cut -c1-200; ls agent/out | head -20; grep -n "disk_low" agent/autotrain/autotrain.sh | head -5
pgrep -fa "distill_v2.py train" | grep -v pgrep | cut -c1-200
