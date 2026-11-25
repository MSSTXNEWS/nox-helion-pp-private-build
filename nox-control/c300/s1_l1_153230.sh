S=/workspace/nox/web/site
cd $S
[ -f x.txt ] && cp -p x.txt x.txt.bak_s1_$(date +%H%M%S)
base64 -d > x.txt <<'S1EOF'
eAo=
S1EOF
echo OK x.txt $(wc -c <x.txt)
cd /workspace/nox/web/site
for p in 8090 8097 8098; do for u in /api/nox/status /api/chat/health /api/turn /api/feedback; do c=$(curl -s -m8 -o /tmp/o1 -w '%{http_code}' http://127.0.0.1:$p$u); echo "$p $u $c $(head -c 120 /tmp/o1 2>/dev/null)"; done; done
grep -o "className *= *['\"]m [^'\"]*['\"]\|classList.add('m'[^)]*)\|class=\"m [^\"]*\"" chat.html nox-chat-x.js nox-chat-tg.js | head -6
grep -n "function addMsg\|function bubble\|function append\|const send\|function send\|async function send" chat.html nox-chat-x.js | head
