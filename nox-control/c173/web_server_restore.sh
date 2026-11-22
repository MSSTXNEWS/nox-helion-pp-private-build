#!/bin/bash
# c173: вернуть на S1 веб-сервер с /api/pc-metrics и /api/health (его перезаписала более ранняя копия «small» из c300),
# не потеряв правки c300: занятость GLM по /slots и подпись GLM-5.3-Flash. Копия: web_server.py.bak-173. Ничего не удаляется.
R=${NOX_RAW:-https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control}; P=/root/nox/web_server.py; N=173
PID=$(pgrep -f "/root/nox/web_server.py" | head -1); ENVF=/tmp/web_env.$N; [ -n "$PID" ] && tr '\0' '\n' < /proc/$PID/environ | grep '^NOX_' > $ENVF || : > $ENVF
echo "env: $(cat $ENVF | tr '\n' ' ')"
[ ! -f $P.bak-$N ] && cp -p $P $P.bak-$N
curl -fsSL $R/s1web/web_server.py -o $P.new && [ -s $P.new ] || { echo "FAIL download"; exit 1; }
python3 -I - $P.new <<'PY'
import re,sys
p=sys.argv[1]; s=open(p,encoding='utf-8').read()
old='c = http.client.HTTPConnection("127.0.0.1", 8081, timeout=2); c.request("GET", "/health"); d["glm_busy"] = c.getresponse().status == 503'
new='c = http.client.HTTPConnection("127.0.0.1", 8081, timeout=2); c.request("GET", "/slots"); d["glm_busy"] = any(x.get("is_processing") for x in json.loads(c.getresponse().read() or b"[]"))'
n=s.count(old); s=s.replace(old,new); s=re.sub(r'GLM-5\.3(?!-Flash)','GLM-5.3-Flash',s)
open(p,'w',encoding='utf-8').write(s); print('busy patch=%d pc_metrics=%d'%(n,s.count('pc_metrics')))
PY
python3 -m py_compile $P.new && mv $P.new $P || { echo "FAIL compile"; rm -f $P.new; exit 1; }
pkill -f "/root/nox/web_server.py"; sleep 1
( set -a; . $ENVF; set +a; nohup setsid python3 $P > /root/nox/logs/web_server.log 2>&1 < /dev/null & )
sleep 4
for u in /api/health /api/pc-metrics /web/chat.html /glm/v1/nox/stats /memory/health; do echo "$u $(curl -s -m10 -o /tmp/c173.b -w '%{http_code}' http://127.0.0.1:8091$u) $(head -c 260 /tmp/c173.b | tr '\n' ' ')"; done
