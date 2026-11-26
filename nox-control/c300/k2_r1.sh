echo "C300: k2_r1"
N=/workspace/nox
echo "--- time/owner"; date; ls -la --time-style=full-iso $N/state/OWNER_ACTIVE 2>&1 | head -2
echo "--- gpu"; nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader
nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader
echo "--- df"; df -h /workspace | tail -1; free -g | head -2
echo "--- supervisor"; supervisorctl status 2>&1 | head -60
echo "--- 8104 proc"; ps -eo pid,ppid,etimes,args | grep -E "llama-server|llama_server" | grep -v grep | cut -c1-400
echo "--- ports"; ss -ltnp 2>/dev/null | grep -E ":(8104|8105|8200|8090|8301|8143|7700|18091)\b" | cut -c1-200
echo "--- supervisor confs"; ls /etc/supervisor/conf.d/ 2>&1 | head -50
echo "--- crontab"; crontab -l 2>&1 | grep -vE "^\s*#" | cut -c1-250
