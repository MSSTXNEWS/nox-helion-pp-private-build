# A: контракт recall_api (только чтение)
grep -rn "empty text" /workspace/nox/brain/MEM /workspace/nox/web/pkg/server 2>/dev/null | grep -v venv | head -3 | cut -c1-220
F=$(grep -rln "empty text" /workspace/nox/brain/MEM /workspace/nox/web/pkg/server 2>/dev/null | grep "\.py$" | head -1); echo "FILE $F"
[ -n "$F" ] && grep -n "op\b\|\"op\"\|'op'\|journal\|budget_tokens\|limit\|empty text\|def " "$F" | head -45 | cut -c1-200
echo "=== web_server handler"; sed -n 286,300p /workspace/nox/web/pkg/server/web_server.py | cut -c1-220
