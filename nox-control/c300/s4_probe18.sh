N=/workspace/nox
echo "S4P18 $(date +%F_%H:%M)"
echo "## char_cycle 1-30"; sed -n 1,30p $N/ops/dpo/char_cycle.sh | cut -c1-330
echo "## char_cycle running?"; pgrep -af "char_cycle" | cut -c1-120 | head -3
echo "## autotrain donor restarts"; ls $N/agent/autotrain/*.sh 2>/dev/null | head; grep -n -E "llama-server|8104|donor_|start_donor|stop_donor|body_restart|mapfile -t ARGS|setsid nohup" $N/agent/autotrain/autotrain.sh 2>/dev/null | cut -c1-260 | head -40
echo "## autotrain running?"; pgrep -af "autotrain.sh" | cut -c1-120 | head -3
echo "## other script callers (ours)"; grep -rIl "body_restart.sh" $N/ops $N/agent/autotrain $N/agent/nox_ops 2>/dev/null | grep -v -E "\.bak|\.orig|\.prev" 
