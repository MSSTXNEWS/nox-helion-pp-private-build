#!/bin/bash
A=https://api.github.com/repos/MSSTXNEWS/nox-helion-pp-private-build/contents/nox-control; H="Accept: application/vnd.github.raw"
g(){ curl -fsSL -H "$H" "$A/$1?ref=main" -o "$2"; }
g web/patch_chat.py /tmp/patch_chat.py; g web/restart.py /tmp/restart.py; g web/files/nox-web-extras.js /root/nox/web/nox-web-extras.js
cp /root/nox/web/nox_mode.js /root/nox/web/nox_mode.js.bak_web2; cp /root/nox/web_server.py /root/nox/web_server.py.bak_web2
python3 /tmp/patch_chat.py && python3 -I -m py_compile /root/nox/web_server.py && python3 /tmp/restart.py 8091 /root/nox/logs/web_server.log
sleep 3; c=$(curl -s -o /dev/null -w %{http_code} http://127.0.0.1:8091/web/chat.html); echo "chat.html $c"
if [ "$c" != 200 ]; then cp /root/nox/web_server.py.bak_web2 /root/nox/web_server.py; python3 /tmp/restart.py 8091 /root/nox/logs/web_server.log; echo ROLLBACK; fi
for m in fast deep; do echo "== $m"; curl -s -m90 http://127.0.0.1:8091/api/chat -H 'Content-Type: application/json' -d "{\"messages\":[{\"role\":\"user\",\"content\":\"привет\"}],\"stream\":true,\"nox_mode\":\"$m\"}" | python3 -c 'import sys,json
t="";n=0
for l in sys.stdin:
  try:o=json.loads(l)
  except: print("RAW",l[:150]);continue
  n+=1;t+=o.get("message",{}).get("content","")
print(n,"lines:",repr(t[:200]))'; done
echo "== fallback test (шлюз на мёртвый порт)"; python3 - <<'P'
import sys,types,json,http.client
sys.argv=['x']; src=open('/root/nox/web_server.py',encoding='utf-8').read()
# прямой вызов _fast_text на 8083
ns={}; i=src.index('    def _fast_text'); j=src.index('    def _fb')
import textwrap; code=textwrap.dedent(src[i:j]); exec("import http.client,json\n"+code,ns)
print(repr(ns['_fast_text'](None,{"messages":[{"role":"user","content":"скажи привет"}],"max_tokens":30})))
P
grep -o "\['max','Максимум'" /root/nox/web/nox_mode.js | head -1; curl -s http://127.0.0.1:8091/web/nox_mode.js | grep -c "Максимум"
