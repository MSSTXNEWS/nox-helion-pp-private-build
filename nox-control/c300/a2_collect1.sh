echo "C300: a2_collect1"
A=/workspace/nox/agents; ls /workspace/nox/state/playbooks; pgrep -af nox_agents.py | head -2; curl -s -m5 127.0.0.1:8810/health | head -c 200; echo
curl -s -m10 127.0.0.1:8810/tasks | python3 -c "
import json,sys,urllib.request
for t in json.load(sys.stdin)[:4]:
    d=json.load(urllib.request.urlopen('http://127.0.0.1:8810/task/'+t['id'],timeout=10))
    st=d.get('steps',[])
    print(t['id'],t['title'],t['status'],'brief',sum(s['kind']=='brief' for s in st),'coach',[s['text'][:100] for s in st if s['kind']=='coach'])
"
curl -s -m5 127.0.0.1:8810/metrics | head -c 500; echo; tail -3 $A/service.log | cut -c1-200
