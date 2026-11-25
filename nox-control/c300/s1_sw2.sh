cd /workspace/nox/web/site
wc -c sw.js; tail -c 3500 sw.js
echo; echo ==SRC; ls /workspace/nox/build_a/src 2>/dev/null | head; grep -rl "workbox" /workspace/nox/build_a/src /workspace/nox/web/build 2>/dev/null | grep -v node_modules | head
grep -n "class=\"send\"\|type=\"submit\"" chat.html | cut -c1-80
