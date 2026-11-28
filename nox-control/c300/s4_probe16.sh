N=/workspace/nox; mask(){ sed -E 's#https://[a-z0-9-]+\.trycloudflare\.com#https://***.trycloudflare.com#g'; }
echo "S4P16 $(date +%F_%H:%M)"
P=1243368; echo "## tunnel 18092 proc"; ps -o pid,ppid,etimes,args -p $P | tail -1 | cut -c1-200; PP=$(ps -o ppid= -p $P | tr -d ' '); ps -o pid,ppid,etimes,args -p $PP | tail -1 | cut -c1-220; PPP=$(ps -o ppid= -p $PP | tr -d ' '); ps -o pid,ppid,args -p $PPP | tail -1 | cut -c1-200
echo "metrics: $(curl -s -m4 http://127.0.0.1:20999/quicktunnel | mask | head -c 200)"; echo "ready: $(curl -s -m4 -o /dev/null -w '%{http_code}' http://127.0.0.1:20999/ready)"
echo "## who starts it"; grep -rIl -e "20999" -e "18092" $N/ops $N/mods $N/agent/*.sh /opt/supervisor-scripts /etc/supervisor/conf.d 2>/dev/null | head -8
echo "## url files"; ls -la --time-style=+%m-%d_%H:%M $N/agent/out/*URL*.txt 2>/dev/null | awk '{print $5,$6,$7}'; for f in $N/agent/out/WEB_CHAT_URL.txt; do [ -f $f ] && echo "WEB_CHAT_URL.txt: $(mask < $f | head -c 100)"; done
echo "## body_restart callers (all)"; grep -rIn "body_restart" $N/ops $N/agent $N/mods $N/brain --include=*.sh --include=*.py 2>/dev/null | grep -v -E "\.bak|\.orig|\.prev|/venv" | grep -v "^$N/ops/body_restart.sh" | cut -c1-210 | head -25
echo "## weekly_exam p1"; sed -n 95,112p $N/mods/weekly_exam.py | cut -c1-230
echo "## brief writers"; grep -rIl --include=*.py --include=*.sh "morning_brief_v5" $N/mods $N/ops $N/agent 2>/dev/null | head -4
echo "## sidecar health"; for p in / /health /ping; do echo "18798$p -> $(curl -s -m3 -o /dev/null -w '%{http_code}' http://127.0.0.1:18798$p)"; done
echo "## qa turn probe"; T0=$(date +%s%N); curl -s -m 60 -N -H 'Content-Type: application/json' -d '{"conversation_id":"qa-uptime-probe","message":"ответь одним словом: да","mode":"fast","user_id":"qa_exam"}' http://127.0.0.1:18091/api/turn | head -c 300 | mask; echo; echo "ms=$(( ($(date +%s%N)-T0)/1000000 ))"
