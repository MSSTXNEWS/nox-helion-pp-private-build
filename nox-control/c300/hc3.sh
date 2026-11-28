echo "K1: hc3"
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits | while IFS=, read p m; do echo "gpu pid=$p mib=$m name=$(ps -o comm= -p $p) port=$(ps -o args= -p $p | grep -oE -- '--port [0-9]+') model=$(ps -o args= -p $p | grep -oE -- '-m [^ ]+' | sed 's#.*/##')"; done
p=$(pgrep -f body_restart.sh | head -1); echo "br_parent=$(ps -o comm= -p $(ps -o ppid= -p $p 2>/dev/null) 2>/dev/null) br_cmdfile=$(ps -o args= -p $p | grep -oE '[^ /]+\.cmd[^ ]*')"
L=$(ls -t /workspace/nox/ops/*restart*.log /workspace/nox/state/*restart*.log 2>/dev/null | head -1); echo "brlog=$L"; tail -n 8 "$L" 2>/dev/null | grep -oE "(wait|vram|free|OOM|fail|ready|timeout|retry|load)[^ ]*[ =:]*[0-9]*" | tr '\n' ' '; echo
echo END
