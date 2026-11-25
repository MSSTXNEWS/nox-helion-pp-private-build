echo "C300: a2_collect2"
pgrep -fc 'python nox_agents.py'; curl -s -m5 127.0.0.1:8810/health | head -c 150; echo
curl -s -m10 127.0.0.1:8810/board | python3 -c "
import json,sys
b=json.load(sys.stdin)
for k,v in b.items():
    for c in v[:6]: print(k,c['id'],c['title'],c['stage'],c['pct'],'eta',c['eta_sec'],'stop:',c['blocker'][:70],'|',c['doing'][:60])
"
curl -s -m10 127.0.0.1:8810/tasks | python3 -c "
import json,sys,urllib.request
for t in json.load(sys.stdin)[:6]:
    d=json.load(urllib.request.urlopen('http://127.0.0.1:8810/task/'+t['id'],timeout=10)); st=d['steps']
    print(t['id'],t['title'],t['status'],'brief',sum(s['kind']=='brief' for s in st),'coach',[s['text'][:80] for s in st if s['kind']=='coach'],'lesson',sum(s['kind']=='lesson' for s in st))
"
curl -s -m5 127.0.0.1:8810/inspect; echo; curl -s -m5 127.0.0.1:8810/metrics | head -c 400; echo
tail -3 /workspace/nox/state/lessons.jsonl | cut -c1-250
