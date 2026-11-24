#!/bin/bash
S=/workspace/nox/web/site
cd $S; wc -c chat.html index.html cinema.html music.html; ls | grep -iv bak | grep -i -E "news|rss|feed|lib|vendor|js|assets"; ls js assets vendor lib 2>/dev/null|head -50
python3 - <<'P'
import json
d=json.load(open('/workspace/nox/web/site/nav.json'))
print(json.dumps(d,ensure_ascii=False)[:1800])
P
echo ===CHAT; cat chat.html | head -c 9000
echo; echo ===GREP; grep -n "api/chat\|localStorage\|function " chat.html | head -80
grep -n "api/chat\|/cal\|route\|def do_POST\|feedback" /workspace/nox/web/pkg/server/web_server.py | head -30
