echo "K1: l1_rc1"
W=$(dirname "$(find /workspace/nox -maxdepth 4 -name chat_core.py -not -path '*/node_modules/*' 2>/dev/null | head -1)")
echo "W=$W"; ls "$W" | head -60
echo "== df"; df -h /workspace | tail -1; free -g | head -2; uptime
echo "== gpu"; nvidia-smi --query-gpu=memory.used,memory.total,temperature.gpu,utilization.gpu --format=csv,noheader
echo "== supervisor"; supervisorctl status 2>&1 | head -40
echo "== ports"; for p in 8104 8105 8793 4000 8090 8091 8300 18217 8400 8082 8796 18091 3001 8888 8080; do printf "%s " $p; curl -s -o /dev/null -m 3 -w "%{http_code}\n" http://127.0.0.1:$p/health; done
echo "== chat_core grep"; grep -n "def \|deadline\|8104\|id_slot\|advisors_unavailable\|chat_fast" "$W/chat_core.py" | head -80
ls /workspace/nox/state 2>/dev/null | head -50; ls $W/state 2>/dev/null | head -30
echo "== restic/rclone/age"; which restic rclone age gitleaks detect-secrets uptime-kuma 2>&1 | head; pip list 2>/dev/null | grep -i -E "detect-secrets|faster-whisper|litellm|whisper" 
