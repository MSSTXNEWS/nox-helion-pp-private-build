grep -n "^DONE" /tmp/r2_audit.log | tail -3
pkill -f r2_queue.sh
pgrep -fa "qa_audit.py" | cut -c1-110
setsid nohup /workspace/nox/r2_queue.sh news models intents about index finance chat atlas constructor pdf assistant scene effects widgets integrations glance install >/dev/null 2>&1 < /dev/null &
sleep 1; pgrep -fa r2_queue | cut -c1-80
