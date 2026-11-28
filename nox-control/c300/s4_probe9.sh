N=/workspace/nox
echo "S4P9 $(date +%F_%H:%M)"
echo "## body_restart"; F=$(find $N /workspace -maxdepth 4 -name "body_restart*.sh" -not -path "*/venv*" 2>/dev/null | head -3); echo "$F"
for f in $F; do echo "### $f $(stat -c %s $f)"; head -c 4500 $f | cut -c1-260; done
echo "## cmd variants"; find $N -maxdepth 4 \( -name "p5_best*" -o -name "gpu_ncmoe*" -o -name "ncmoe*" \) -not -path "*/venv*" 2>/dev/null | head -12
echo "## gpu"; nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader; nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader | head
echo "## llama procs"; ps -eo pid,args | grep -E "llama-server" | grep -v grep | cut -c1-330 | head -8
echo "## supervisor body"; supervisorctl status 2>/dev/null | grep -i -E "body|llama|nox_core|gpu" | head
