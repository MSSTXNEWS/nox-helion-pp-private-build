echo "C300: ac_chat3"
P=$(pgrep -f "port 8104" | head -1); echo "ppid $(ps -o ppid= -p $P)"; ps -o pid,args -p $(ps -o ppid= -p $P) | tail -1 | cut -c1-200
supervisorctl status 2>/dev/null | grep -iE "8104|chat|llama" | head -5
grep -rln "port 8104" /etc/supervisor /workspace/nox/ops/*.sh /workspace/nox/serve/*.sh 2>/dev/null | head -5
uptime; cat /workspace/nox/state/train_phase* 2>/dev/null | head -2
curl -s -m3 127.0.0.1:8104/slots | python3 -c "import sys,json;print([s['is_processing'] for s in json.load(sys.stdin)])"
curl -sL https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/chat_bench.py -o /tmp/cb.py
for i in 1 2; do python3 /tmp/cb.py 2>&1 | tail -2; done
