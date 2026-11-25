echo S4RUN:l_impl2
cd /workspace/nox/web/pkg/server
python3 -c "
import chat_core as c
p=c._persona_prefix(); print('PREFIX_OK', len(p), len(p[0]['content']) if p else 0); print(p[0]['content'][:200] if p else '')" 2>&1 | tail -5
curl -s -m 150 -X POST localhost:8091/api/turn -H 'Content-Type: application/json' -d '{"conversation_id":"ltest2","message":"Мне тревожно, кажется, все меня ненавидят."}' | head -c 1800
echo; curl -s -m 10 localhost:8091/api/health | head -c 200
