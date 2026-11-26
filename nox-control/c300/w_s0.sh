echo "C300: w_s0"
N=/workspace/nox
F=$(ls $N/web/web_server.py $N/*/web_server.py 2>/dev/null | head -1); echo "F=$F"
grep -n -i -E "search|web_fetch|/api/(web|research|sources|rag)" "$F" 2>/dev/null | cut -c1-160 | head -20
for p in /api/search /api/web/search /api/websearch /api/research /api/sources /api/nox/search; do echo -n "$p "; curl -s -m 5 -o /dev/null -w '%{http_code}\n' "http://127.0.0.1:8091$p?q=test"; done
ls $N/web/site/hls* $N/web/site/vendor/hls.js/dist 2>/dev/null | head -3; ls $N/web/site/vendor/vidstack | head
