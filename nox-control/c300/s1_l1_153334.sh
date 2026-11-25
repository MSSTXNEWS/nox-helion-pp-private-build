S=/workspace/nox/web/site
cd $S
[ -f x.txt ] && cp -p x.txt x.txt.bak_s1_$(date +%H%M%S)
base64 -d > x.txt <<'S1EOF'
eAo=
S1EOF
echo OK x.txt $(wc -c <x.txt)
cd /workspace/nox/web/site
for u in /api/nox/status /api/chat/health /api/turn /api/feedback; do c=$(curl -s -m8 -o /tmp/o1 -w '%{http_code}' http://127.0.0.1:8091$u); echo "EP $u $c $(head -c 160 /tmp/o1)"; done
grep -n "btnSend" chat.html nox-chat-x.js | head -5
grep -o "id=\"feed\"[^>]*" chat.html | head -2
grep -n "classList.add('m'\|className *= *'m\|class=\\\\\"m \|'<div class=\"m " chat.html nox-*.js | head -6 | cut -c1-220
