#!/bin/bash
# s2_recon1.sh: чтение: страницы cinema/music/news/studio, nox-empty-x, мост Диска, диск
S=/workspace/nox/web/site
df -h /workspace | tail -1
for f in cinema music news studio; do echo "=== $f.html $(wc -c <$S/$f.html)"; grep -o '<script[^>]*src="[^"]*"\|<link[^>]*href="[^"]*"' $S/$f.html | cut -c1-120; grep -c . $S/$f.html; done
echo "== cinema body"; sed -n '1,400p' $S/cinema.html | cut -c1-260 | head -120
echo "== empty-x"; wc -c $S/nox-empty-x.js $S/nox-empty-x.css; head -c 3500 $S/nox-empty-x.js
echo "== vendor"; ls $S/vendor | tr '\n' ' '
echo "== bridge"
ps aux | grep -i 18765 | grep -v grep | cut -c1-200
grep -rln "18765" /workspace/nox --include=*.py --include=*.sh --include=*.json 2>/dev/null | grep -v venv | head -5
for p in / /health /files /list /api/files /drive/health; do printf "%s -> " $p; curl -s -o /tmp/s2_b.txt -w "%{http_code} " --max-time 5 http://127.0.0.1:18765$p; head -c 200 /tmp/s2_b.txt; echo; done
grep -n '/drive' /workspace/nox/web/pkg/server/web_server.py | head -10 | cut -c1-200
ls /workspace/nox/web/site/vendor/cinema_pkg 2>&1 | head
ls /workspace/nox/web/site/qa/rework | head -30
