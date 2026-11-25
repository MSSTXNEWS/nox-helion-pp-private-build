echo "C300: a2_diag3"
A=/workspace/nox/agents
echo "== deep"; head -c 1200 $A/cons_deep.json; echo; echo "== scan2"; head -c 300 $A/scan2.json; echo
echo "== c1 steps"; curl -s -m10 127.0.0.1:8810/task/1125-1e94af | python3 -c "
import json,sys,time;d=json.load(sys.stdin);print(d['status'],d.get('tokens'),'restarts',d['restarts'])
for s in d['steps'][-12:]: print(int(time.time()-s['ts']),'s ago',s['kind'],s['text'][:110].replace('\n',' '))"
echo "== llm latency"; for b in 8104 8141 8811; do /usr/bin/time -f "$b %es" curl -s -m 100 127.0.0.1:$b/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"x","messages":[{"role":"user","content":"скажи ок"}],"max_tokens":5}' | head -c 150; echo; done
echo "== slots"; curl -s -m5 127.0.0.1:8104/slots | python3 -c "
import json,sys
for s in json.load(sys.stdin): print(s['id'],'busy' if s['is_processing'] else 'idle',s.get('n_decoded'))"
ss -tn state established '( sport = :8104 )' 2>/dev/null | wc -l
grep -iE "error|Traceback|Timeout" $A/service.log | tail -8 | cut -c1-200
cat /workspace/nox/state/agent_backends.json | head -c 400
