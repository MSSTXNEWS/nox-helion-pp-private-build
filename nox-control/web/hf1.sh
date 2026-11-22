#!/bin/bash
# stage1: патч во временный файл, компиляция, тест на временном порту 8099 (прод не трогаем)
cd /root/nox; W=/root/nox/web_server.py
curl -fsSL -H "Accept: application/vnd.github.raw" "https://api.github.com/repos/MSSTXNEWS/nox-helion-pp-private-build/contents/nox-control/web/wow7/hf_patch_web.py?ref=main" -o /tmp/hf_patch_web.py || { echo fetch fail; exit 1; }
python3 -I /tmp/hf_patch_web.py $W /root/nox/web_server.py.hfnew || exit 1
python3 -I -m py_compile /root/nox/web_server.py.hfnew && echo compiled
grep -n "^PORT\|PORT =" $W | cut -c1-160 | head -3
pid=$(ss -ltnp | grep ":8091 " | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2)
echo "prod env: $(tr '\0' '\n' </proc/$pid/environ | grep -E '^(NOX_SMALL_OFF|NOX_DEEP_DIRECT|NOX_WEB_PORT|PORT|NOX_GW)' | tr '\n' ' ')"
tr '\0' '\n' </proc/$pid/environ | grep -E '^(NOX|PORT)' > /tmp/hf_env.txt
cp /root/nox/web_server.py.hfnew /root/nox/web_server_hftest.py
( set -a; . <(sed 's/^\([^=]*\)=\(.*\)$/\1="\2"/' /tmp/hf_env.txt) 2>/dev/null; set +a
  NOX_SMALL_OFF=0 PORT=8099 NOX_WEB_PORT=8099 nohup python3 /root/nox/web_server_hftest.py >/tmp/hftest.log 2>&1 & echo $! > /tmp/hftest.pid )
sleep 4; head -c 200 /tmp/hftest.log
ask(){ curl -sN -m60 http://127.0.0.1:8099/api/chat -H 'Content-Type: application/json' -d "{\"messages\":[{\"role\":\"user\",\"content\":\"$1\"}],\"stream\":true,\"nox_mode\":\"fast\"}" | python3 -c "
import sys,json
t='';ph=[]
for l in sys.stdin:
    try: o=json.loads(l)
    except Exception: continue
    t+=(o.get('message') or {}).get('content','')
    if o.get('nox_phase'): ph.append(o['nox_phase'].get('phase'))
    if o.get('error'): t+='[ERR '+str(o['error'])[:80]+']'
print(repr(t[:300]),ph)"; }
for q in "привет" "привет" "привет" "как сервер?"; do echo "Q:$q -> $(ask "$q")"; done
kill $(cat /tmp/hftest.pid) 2>/dev/null; rm -f /root/nox/web_server_hftest.py; tail -c 300 /tmp/hftest.log
