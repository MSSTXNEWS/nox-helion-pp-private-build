echo "C300: ch_ag2"
A=/workspace/nox/agent/nox_agents
sed -n 120,226p $A/supervisor.py | cut -c1-200
echo "=== chat_speed_watch"; sed -n 1,40p $A/chat_speed_watch.py | cut -c1-180
echo "=== agents list"; grep -rn "chat_speed_watch" $A/*.py /workspace/nox/agent/*.sh 2>/dev/null | cut -c1-200 | head
echo "== golden4"; cat /workspace/nox/state/ch_golden4.out | cut -c1-230
