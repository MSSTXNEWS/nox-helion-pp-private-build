echo "C300: c_dbg3"
for m in pollinations/openai kilo/baidu/ernie-5.5-flash-preview:free auto; do echo "== $m"; /bin/bash -c "S=\$(date +%s); curl -s -m25 localhost:8793/v1/chat/completions -H 'Content-Type: application/json' -d '{\"model\":\"$m\",\"messages\":[{\"role\":\"system\",\"content\":\"Отвечай по-русски. [nc1]\"},{\"role\":\"user\",\"content\":\"Столица Италии?\"}],\"max_tokens\":60}' | cut -c1-420; echo; echo dt=\$((\$(date +%s)-S))"; done
curl -s -m10 localhost:8793/v1/models | python3 -c "
import sys,json
d=json.load(sys.stdin)['data']
for m in d:
    if m.get('available') and m.get('status')=='ok' and not m.get('needs_key'): print(m['id'],m.get('latency_ms'))"
ls /workspace/nox/state/*gw* /workspace/nox/svc/*/gateway* 2>/dev/null | head; pgrep -fa "8793|gateway" | cut -c1-150 | head -3
