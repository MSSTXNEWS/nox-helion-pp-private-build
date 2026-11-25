echo "== CC1"; find /workspace/nox -name chat_core.py -not -path "*/node_modules/*" -not -path "*/venv/*" 2>/dev/null | head
F=$(find /workspace/nox/web -name chat_core.py 2>/dev/null | head -1); echo F=$F; wc -l $F
grep -n "system\|messages\|def " $F | cut -c1-190 | head -60
