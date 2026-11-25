S=/workspace/nox/web/site
cd $S
[ -f x.txt ] && cp -p x.txt x.txt.bak_s1_$(date +%H%M%S)
base64 -d > x.txt <<'S1EOF'
eAo=
S1EOF
echo OK x.txt $(wc -c <x.txt)
cd /workspace/nox/web/site
for u in /api/nox/status /api/chat/health /api/turn /api/feedback; do echo "$u $(curl -s -m8 -o /tmp/o -w '%{http_code}' http://127.0.0.1:8080$u 2>&1) $(head -c 200 /tmp/o)"; done
ss -ltnp 2>/dev/null | grep -E ':80[0-9][0-9]|:18[0-9]{3}' | head -5
grep -o 'id="btnSend"[^>]*' chat.html | head -2
grep -o 'class="m [a-z ]*"' chat.html | head -3
grep -n "function send\|async function send\|function addMsg\|function renderMsg\|\.m\.bot\|class=\"acts\"" chat.html | head -12
grep -o "\(nox-chat-[a-z]*\|nox-[a-z0-9-]*\)\.js" chat.html | sort -u | tr '\n' ' '
