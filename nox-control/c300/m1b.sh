cd /workspace/nox/web
grep -n '"/api/chat"' pkg/server/web_server.py | head -5 | cut -c1-200
grep -n "def _turn" -A30 pkg/server/web_server.py | cut -c1-210 | head -50
grep -rn "api/chat" site/nox-*.js | grep -v "health\|conv" | head -6 | cut -c1-260
