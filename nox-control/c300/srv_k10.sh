echo "C300: srv_k10"
A=/workspace/nox/agents; cd $A
P=$(ss -ltnp | grep ":8810 " | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2); kill $P; sleep 4
setsid -f nohup $A/venv/bin/python nox_agents.py </dev/null >>service.log 2>&1
sleep 15
curl -s -m 10 -o /dev/null -w "8810 %{http_code}\n" http://127.0.0.1:8810/worms/night
curl -s -m 200 -X POST http://127.0.0.1:8810/worms/night/run | head -c 300; echo
sleep 60; curl -s -m 10 http://127.0.0.1:8810/worms/night | tail -c 300; echo
tail -3 worms.err
