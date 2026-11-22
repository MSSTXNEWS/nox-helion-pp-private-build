#!/bin/bash
A=https://api.github.com/repos/MSSTXNEWS/nox-helion-pp-private-build/contents/nox-control
H="Accept: application/vnd.github.raw"; W=/root/nox/web
g(){ curl -fsSL -H "$H" "$A/$1?ref=main" -o "$2"; }
g web/restart.py /tmp/restart.py; g web/patch_srv.py /tmp/patch_srv.py; g qs6/recall_api.py /tmp/ra_new.py
for f in nox-web-extras.js nox-web-extras.css templates.html; do g web/files/$f $W/$f.new && mv $W/$f.new $W/$f; done
echo "== 1 recall_api"
R=/root/nox/repo/nox-control/qs6/recall_api.py
if ! grep -q 'op == "list"' $R; then cp $R $R.bak_web; python3 -I - <<'P'
n=open('/tmp/ra_new.py').read(); i=n.index('            if op == "list":'); j=n.index('            if op == "search":')
r='/root/nox/repo/nox-control/qs6/recall_api.py'; s=open(r).read(); a='            if op == "search":\n'
assert a in s; open(r,'w').write(s.replace(a,n[i:j]+a,1)); print('patched recall_api')
P
python3 -I -m py_compile $R && python3 /tmp/restart.py 8095 /root/nox/logs/recall_server.log; sleep 4; fi
curl -s -m5 http://127.0.0.1:8091/memory/health | head -c 120; echo
curl -s -m8 -X POST http://127.0.0.1:8091/memory/api -H 'Content-Type: application/json' -d '{"op":"list","limit":3}' | head -c 400; echo
echo "== 2 gzip"
cp -n /root/nox/web_server.py /root/nox/web_server.py.bak_web
python3 /tmp/patch_srv.py && python3 -I -m py_compile /root/nox/web_server.py && python3 /tmp/restart.py 8091 /root/nox/logs/web_server.log
sleep 3
c=$(curl -s -o /dev/null -w %{http_code} http://127.0.0.1:8091/web/chat.html)
if [ "$c" != 200 ]; then echo "ROLLBACK ($c)"; cp /root/nox/web_server.py.bak_web /root/nox/web_server.py; python3 /tmp/restart.py 8091 /root/nox/logs/web_server.log; sleep 3; curl -s -o /dev/null -w "after rollback %{http_code}\n" http://127.0.0.1:8091/web/chat.html
else curl -s -H 'Accept-Encoding: gzip' -D- -o /dev/null http://127.0.0.1:8091/web/nox-newchat.js | grep -i "content-encoding\|content-length\|cache-control"; curl -s -o /dev/null -w "raw %{size_download} gz %{size_download}\n" http://127.0.0.1:8091/web/nox-newchat.js; curl -s -H 'Accept-Encoding: gzip' -o /dev/null -w "gz %{size_download}\n" http://127.0.0.1:8091/web/nox-newchat.js; fi
echo "== 3 voice"
for u in stt/health tts/health stt/ tts/; do echo "$u $(curl -s -m4 -o /dev/null -w %{http_code} http://127.0.0.1:8091/$u)"; done | tr '\n' ' '; echo; curl -s -m4 http://127.0.0.1:8093/health | head -c 200; echo; curl -s -m4 http://127.0.0.1:8094/health | head -c 200; echo
echo "== 4 cleanup"; b=$(df --output=avail -B1M /root | tail -1)
npm cache clean --force >/dev/null 2>&1; rm -rf /tmp/npmw /root/.npm/_cacache; pip cache purge >/dev/null 2>&1; apt-get clean >/dev/null 2>&1; rm -rf /var/lib/apt/lists/*
a=$(df --output=avail -B1M /root | tail -1); echo "freed $((a-b)) MB"; du -sh /root/.cache/* 2>/dev/null | sort -h | tail -4; ls /root/nox/dl | head -12 | tr '\n' ' '; du -sh /root/nox/dl/* 2>/dev/null | sort -h | tail -5; df -h /root | tail -1
