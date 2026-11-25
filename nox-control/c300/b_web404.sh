#!/bin/bash
# b_web404.sh: откуда префикс /web у запросов фронта и какие пути живы на :8091 (только чтение)
set -u
W=/workspace/nox; S=$W/web/site
echo "== curl 8091"
for p in /api/chat/health /web/api/chat/health /glm/v1/nox/stats /web/glm/v1/nox/stats /health; do printf "%s -> " $p; curl -s -o /dev/null -w "%{http_code}\n" --max-time 5 http://127.0.0.1:8091$p; done
echo "== source of /web/ prefix"
grep -rln "'/web/\|\"/web/\|/web/api\|/web/glm" $S --include=*.js --include=*.html 2>/dev/null | head -10
grep -rn "/web/api\|/web/glm" $S --include=*.js 2>/dev/null | head -6 | cut -c1-220
echo "== base/prefix defs"
grep -rn "BASE\s*=\|PREFIX\s*=\|apiBase\s*=" $S/nox-api.js $S/nox-nav.js 2>/dev/null | head -8 | cut -c1-220
echo "== web_server route for /web/"
grep -n '"/web' $W/web/pkg/server/web_server.py | head -5 | cut -c1-200
