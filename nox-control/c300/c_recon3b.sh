#!/bin/bash
N=/workspace/nox
echo "== JudgeIn"; curl -s -m5 localhost:8300/openapi.json | python3 -c "
import json,sys; d=json.load(sys.stdin); s=d['components']['schemas']
for k in ('JudgeIn','TextIn'): print(k,json.dumps(s[k],ensure_ascii=False))"
echo "== judge src"; sed -n 286,430p $N/judges/judge_service.py | cut -c1-200
echo "== judge call"; T0=$(date +%s.%N); curl -s -m40 localhost:8300/judge -H 'Content-Type: application/json' -d '{"text":"Столица Австралии - Канберра.","context":"Столица Австралии?"}' | head -c 1800; echo; echo "dt=$(echo "$(date +%s.%N)-$T0"|bc)"
echo "== factcheck"; curl -s -m30 localhost:8300/factcheck -H 'Content-Type: application/json' -d '{"text":"Столица Австралии - Сидней."}' | head -c 600; echo
echo "== advisor"; T0=$(date +%s.%N); curl -s -m60 localhost:8793/v1/chat/completions -H 'Content-Type: application/json' -d '{"model":"auto","messages":[{"role":"user","content":"Столица Австралии? Одно слово."}],"max_tokens":20}' | head -c 600; echo; echo "dt=$(echo "$(date +%s.%N)-$T0"|bc)"
echo "== llama-swap models"; curl -s -m3 localhost:8200/v1/models | python3 -c "import json,sys;print([m['id']+':'+m['status']['value'] for m in json.load(sys.stdin)['data']])"
echo "== core backend"; grep -n "^GLM\|^RTE\|^CORE\|8090\|8104" $N/web/pkg/server/chat_core.py | head; curl -s -m3 localhost:8090/health | head -c 300; echo
echo "== web search tool?"; ls $N/agent 2>/dev/null | grep -i -E "search|web|searx|ddg" | head; grep -rl "duckduckgo\|searx" $N/agent $N/svc 2>/dev/null | head -5
