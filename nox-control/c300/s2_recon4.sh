#!/bin/bash
S=/workspace/nox/web/site
for f in nox-music-x.js nox-news-x.js nox-studio-x.js; do echo "=== $f"; grep -o "fetch([^)]*)\|import('[^']*')\|NOX\.[a-zA-Z]*\|/music/[a-z_/]*\|/img/[a-z_/]*\|/api/[a-z_/-]*" $S/$f | sort | uniq -c | head -25; done
grep -n "Сводк" $S/nox-news-x.js | cut -c1-600 | head -5
sed -n '/img\/generate/p' $S/nox-studio-x.js | cut -c1-900 | head -4
grep -n "8102\|music/" $S/nox-music-x.js | cut -c1-500 | head -8
grep -rn "/music/\|'/img/" /workspace/nox/web/pkg/server/web_server.py | head -8 | cut -c1-240
curl -s -m5 -X POST http://127.0.0.1:8091/img/generate -H 'Content-Type: application/json' -d '{}' | head -c 300; echo
curl -s -m5 http://127.0.0.1:8091/svc/jellyfin/System/Info/Public | head -c 300; echo
curl -s -m5 http://127.0.0.1:8091/svc/navidrome/rest/ping.view?f=json | head -c 200; echo
curl -s -m5 -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8091/svc/freshrss/
grep -n "export\|window\.NOX\|nox:cmd\|CustomEvent" $S/nox-ninja.js | head -8 | cut -c1-200
