echo S4RUN:s6_p22
for u in /music.html /web/music.html /site/music.html; do echo $u $(curl -s -o /tmp/o.html -w "%{http_code} %{size_download}" http://127.0.0.1:8300$u); done
grep -n "8091\|add_argument\|--port\|site" /workspace/nox/web/web_server.py | head -8
ls /workspace/nox/web | head
