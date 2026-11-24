python3 -c "
import json;d=json.load(open('/workspace/nox/web/site/qa/audit.json'));print('VR',d['chat'].get('vision_raw','')[:300])
r=json.load(open('/workspace/nox/web/site/qa/report.json'))
from collections import Counter;c=Counter(x.split(':')[0][:50] for p in r['pages'].values() for vp in p.values() for x in vp);print(c.most_common(12))"
grep -rl "glm/v1" /workspace/nox/web/site/*.js | head; grep -n "glm" /workspace/nox/web/pkg/server/web_server.py | head -5
for u in 127.0.0.1:8090/v1/nox/stats 127.0.0.1:8090/v1/models 127.0.0.1:8200/v1/models 127.0.0.1:4000/v1/models 127.0.0.1:8104/v1/models; do echo "$u $(curl -s -o /dev/null -w '%{http_code}' -m5 http://$u)"; done
ss -ltnp | grep -E "LISTEN" | awk '{print $4}' | sort -u | tr '\n' ' '
