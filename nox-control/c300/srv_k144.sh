echo "C300: srv_k144"
cd /workspace/nox/web/pkg/server
grep -n "думает долго\|advisors_un\|enable_thinking\|max_tokens\|FIRST_\|local_wait\|_LOCAL\|timeout\|backend\b" chat_core.py | cut -c1-200 | head -50
