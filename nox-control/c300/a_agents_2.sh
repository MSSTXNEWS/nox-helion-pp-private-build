echo "== GPU procs"; nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader
echo "== llama-server procs"; ps -eo pid,etimes,args | grep -E 'llama-server|llama-swap|train|python.*(judge|advis|cascade|operator|dispatch|arbiter)' | grep -v grep | cut -c1-420
echo "== listeners 8130/8200/8300/8400/8091/8104"; for p in 8130 8200 8300 8400 8091 8104 18200 18091; do echo "$p $(curl -s -m 3 -o /dev/null -w '%{http_code}' 127.0.0.1:$p/v1/models) $(curl -s -m 3 127.0.0.1:$p/v1/models | head -c 200)"; done
echo "== qwen3.6 model files"; find /workspace/nox/models -maxdepth 5 \( -iname '*35B*' -o -iname '*qwen3.6*' -o -iname '*coder*' \) 2>/dev/null | head -20; 
echo "== config.json 35B"; for f in $(find /workspace/nox/models -maxdepth 6 -iname config.json -path '*35B*' 2>/dev/null | head -2); do python3 -c "import json,sys;c=json.load(open('$f'));c=c.get('text_config',c);print({k:c.get(k) for k in ['num_hidden_layers','num_attention_heads','num_key_value_heads','head_dim','hidden_size','layer_types','full_attention_interval','num_experts']})"; done
echo "== arbiter"; find /workspace/nox -maxdepth 3 -iname '*arbiter*' 2>/dev/null | head; 
echo "== svc_registry"; grep -rl svc_registry /workspace/nox --include=*.py --include=*.sh --include=*.json -s 2>/dev/null | head -5
echo "== advisors"; ls /workspace/nox/advisors 2>&1 | head; ls /workspace/nox/state | grep -iE 'advis|owner|team|task' ; head -c 600 /workspace/nox/state/advisors_external.json 2>&1 | sed -E 's/("(api_)?key"[^,]*)/"key":"<hidden>"/Ig'
echo "== env key names"; for f in /workspace/nox/advisors/*.env /workspace/nox/secrets/*; do [ -f "$f" ] && echo "$f $(wc -c <$f)b"; done 2>/dev/null | head
env | grep -ioE '^[A-Z_]*(OPENROUTER|GROQ|GEMINI|CEREBRAS)[A-Z_]*' | head
echo "== py"; ls /workspace/nox/venv/bin/python /workspace/nox/venv_living/bin/python 2>&1; /workspace/nox/venv/bin/pip list 2>/dev/null | grep -iE 'langgraph|smolagents|huey|persist|fastapi|flask|aiohttp|httpx|openai'
echo "== load"; uptime; ls /workspace/nox/state/*.json | head -40
