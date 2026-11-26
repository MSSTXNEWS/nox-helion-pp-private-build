echo "C300: srv_k147"
renice -n 19 -p $(pgrep -f "distill_v2.py train") 841 >/dev/null 2>&1
for p in $(pgrep -f "Qwen3-30B-A3B-Instruct-2507") $(pgrep -f "port 8141") $(pgrep -f "port 8811"); do renice -n 10 -p $p >/dev/null 2>&1; done
for p in $(pgrep -f "distill_v2.py train") $(pgrep -f "Qwen3-30B-A3B-Instruct-2507") $(pgrep -f "port 8141") $(pgrep -f "port 8144") $(pgrep -f "port 8811") 841; do echo "pid $p nice $(ps -o ni= -p $p)"; done
echo "--- RTE :8084"; tr '\0' ' ' </proc/3627254/cmdline | cut -c1-200; echo
ls /workspace/nox/rte 2>/dev/null | head; ls -t /workspace/nox/rte/*.log /workspace/nox/state/rte*.log 2>/dev/null | head -3
for f in $(ls -t /workspace/nox/rte/*.log /workspace/nox/state/rte*.log 2>/dev/null | head -2); do echo "== $f"; tail -n 8 $f | cut -c1-220; done
