#!/bin/bash
N=/workspace/nox; P=$N/web/pkg/server
echo "== run_turn"; sed -n 322,440p $P/chat_core.py | cut -c1-230
echo "== judges openapi"; curl -s -m5 localhost:8300/openapi.json | python3 -c "
import json,sys; d=json.load(sys.stdin)
for p,v in d['paths'].items():
  for m,o in v.items(): print(m.upper(),p,json.dumps((o.get('requestBody') or {}).get('content',{}).get('application/json',{}).get('schema',{}))[:400])
print(json.dumps(d.get('components',{}).get('schemas',{}))[:2500])"
echo "== judges list"; curl -s -m5 localhost:8300/judges | head -c 1500; echo
echo "== judge_service head"; ls $N/judges | head -30; grep -n "@app\.\|def " $N/judges/judge_service.py | head -50
echo "== advisor probe"; curl -s -m25 localhost:8793/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"auto","messages":[{"role":"user","content":"Столица Австралии? Одно слово."}],"max_tokens":20}' | head -c 500; echo
echo "== persona"; python3 -c "import json;print(json.dumps(json.load(open('$N/state/persona.json')),ensure_ascii=False)[:600])"
echo "== webserver _turn"; sed -n '/def _turn/,/def _chat/p' $P/web_server.py | cut -c1-220 | head -70
echo "== glm/llama"; curl -s -m3 localhost:8200/v1/models | head -c 600; echo; curl -s -m3 localhost:8104/health | head -c 200; echo
