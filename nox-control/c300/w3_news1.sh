cd /workspace/nox/web/site; for p in chat index cinema music; do rm -f qa/rework/$p.fixed; touch qa/rework/$p.fixed; done
python3 - <<'P'
import json
d=json.load(open('/workspace/nox/web/site/nav.json'))
for g in d['groups']:
    for i in g['items']:
        if any(k in (i['title']+i['file']).lower() for k in ('новост','news','board','доска','rss','лент')): print(i)
P
sed -n '12,40p' board.html | cut -c1-600
curl -s -m 8 127.0.0.1:8091/svc/_status | head -c 800; echo
curl -s -m 8 -o /dev/null -w "%{http_code}\n" 127.0.0.1:8091/svc/freshrss/api/greader.php
curl -s -m 8 127.0.0.1:8091/svc/freshrss/api/greader.php | head -c 300
