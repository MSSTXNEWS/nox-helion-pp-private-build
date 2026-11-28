echo "K1: hc1"; N=/workspace/nox
echo "h8104=$(curl -s -o /dev/null -m 5 -w %{http_code} http://127.0.0.1:8104/health)"
echo "body_restart=$(pgrep -fc body_restart.sh) llama=$(pgrep -fc llama-server) train=$(pgrep -f train_dpo.py | head -1) state=$(ps -o stat= -p $(pgrep -f train_dpo.py | head -1) 2>/dev/null)"
echo "cmd_gpu=$(pgrep -af llama-server | grep -c -- '--n-cpu-moe 0\b\|ncmoe0') vram=$(nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader,nounits | tr -d ' ')"
grep -o "mix rows[^\n]*" $N/ops/dpo/run7.log 2>/dev/null | tail -1 | tr -cd '0-9a-z=_ ,\n'
tail -c 300 $N/ops/dpo/run7.log 2>/dev/null | grep -oE "(step|loss)[ =:]*[0-9.]+" | tail -4 | tr '\n' ' '; echo
ls -ld /home/claude/brain/BODY_LOCK 2>/dev/null; echo "disk_free_gb=$(df -BG /workspace | awk 'NR==2{print $4}')"
echo END
