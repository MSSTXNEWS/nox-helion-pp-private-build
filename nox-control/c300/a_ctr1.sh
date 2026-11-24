# A: контракт /memory/api (только чтение)
grep -rn "empty text" /workspace/nox --include=*.py 2>/dev/null | head -5
F=$(grep -rln "empty text" /workspace/nox --include=*.py 2>/dev/null | head -1)
echo "FILE $F"
[ -n "$F" ] && grep -n "def \|op\b\|'op'\|\"op\"\|journal\|core\|budget_tokens\|limit\|text" "$F" | head -60 | cut -c1-200
