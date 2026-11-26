echo "C300: ch_ag3"
A=/workspace/nox/agent/nox_agents
sed -n 25,100p $A/supervisor.py | cut -c1-190
echo === tick of chat_speed_watch; grep -n "def tick" -A22 $A/chat_speed_watch.py | cut -c1-170 | head -40
echo === lib names; grep -n "^def \|^[A-Z_]* *=" $A/lib.py | cut -c1-120 | head -40
