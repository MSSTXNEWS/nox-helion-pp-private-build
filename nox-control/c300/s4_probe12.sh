N=/workspace/nox; W=$N/web/pkg/server/web_server.py
echo "S4P12 $(date +%F_%H:%M)"
grep -n -E "PORT|port *=|\"/api/turn\"|/api/turn/|auth|token|X-NOX|def _auth|owner" $W | head -40 | cut -c1-200
echo "## turn handler"; L=$(grep -n 'p == "/api/turn"' $W | head -1 | cut -d: -f1); [ -n "$L" ] && sed -n "$((L)),$((L+22))p" $W | cut -c1-240
echo "## listening"; ss -ltn | grep -E ":(80|8080|8088|8090|8084|8000|8765|18[0-9]{3}) " | awk '{print $4}' | tr '\n' ' '
echo; echo "## existing stop test"; ls $N/ops $N/mods $N/state/core 2>/dev/null | grep -i -E "stop" ; grep -rIl --include=*.py "stop_max_s\|STOP.*10" $N/mods $N/ops 2>/dev/null | head -4
echo "## weekly_exam stop row"; grep -n -i "stop" $N/mods/weekly_exam.py | head -10 | cut -c1-200
