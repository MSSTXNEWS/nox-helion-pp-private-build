#!/bin/bash
python3 - <<'P'
p='/root/nox/web_server.py'; s=open(p,encoding='utf-8').read()
a='and (ctype.startswith("text/") or "javascript" in ctype'
assert a in s
if 'event-stream' not in s.split(a)[0][-200:]:
    s=s.replace(a,'and not ("event-stream" in ctype or "ndjson" in ctype or "stream" in ctype) and (ctype.startswith("text/") or "javascript" in ctype',1); open(p,'w',encoding='utf-8').write(s); print('excluded streams')
P
python3 -I -m py_compile /root/nox/web_server.py || exit 1
grep -n "def _proxy" -A14 /root/nox/web_server.py | cut -c1-200 | head -18
grep -n "ThreadingHTTPServer" /root/nox/web_server.py | head -2
H='{"messages":[{"role":"user","content":"привет"}],"stream":true,"nox_mode":"fast"}'
echo "== через 8091 (gzip как браузер)"; curl -sN -m60 -H 'Accept-Encoding: gzip, deflate' -D /tmp/h.txt -o /dev/null -w "ttfb=%{time_starttransfer} total=%{time_total} size=%{size_download}\n" http://127.0.0.1:8091/api/chat -H 'Content-Type: application/json' -d "$H"; grep -i "content-encoding\|transfer\|content-type" /tmp/h.txt
echo "== первые строки потока"; curl -sN -m60 http://127.0.0.1:8091/api/chat -H 'Content-Type: application/json' -d "$H" | head -3 | cut -c1-140
echo "== 8082 напрямую SSE"; curl -sN -m60 -o /dev/null -w "ttfb=%{time_starttransfer} total=%{time_total}\n" http://127.0.0.1:8082/v1/chat/completions -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"привет"}],"stream":true,"nox_mode":"fast"}'
echo "== параллель: deep висит, fast отвечает?"; (curl -s -m90 -o /dev/null http://127.0.0.1:8091/api/chat -H 'Content-Type: application/json' -d '{"messages":[{"role":"user","content":"расскажи длинно про звёзды"}],"stream":true,"nox_mode":"deep"}' &) ; sleep 2; curl -sN -m60 -o /dev/null -w "fast при deep: ttfb=%{time_starttransfer} total=%{time_total}\n" http://127.0.0.1:8091/api/chat -H 'Content-Type: application/json' -d "$H"; curl -s -o /dev/null -w "static при deep: %{time_total}\n" http://127.0.0.1:8091/web/chat.html
