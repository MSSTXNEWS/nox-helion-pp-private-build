S=/workspace/nox/web/site
cd $S
[ -f x.txt ] && cp -p x.txt x.txt.bak_s1_$(date +%H%M%S)
base64 -d > x.txt <<'S1EOF'
eAo=
S1EOF
echo OK x.txt $(wc -c <x.txt)
ss -ltnp | grep -E ':8091|:8300|:8793|:8090|:8084|:8097|:8098' | cut -c1-140
for p in 8091 8300 8793 8090; do echo "== $p $(curl -s -m4 -o /dev/null -w '%{http_code}' http://127.0.0.1:$p/)"; done
curl -s -m4 http://127.0.0.1:8300/health | head -c 300; echo; curl -s -m4 http://127.0.0.1:8793/health | head -c 300; echo
find /workspace/nox -name "chat_core*" -not -path "*/node_modules/*" 2>/dev/null | head -5
find /workspace/nox -name "web_server.py" 2>/dev/null | head -3
ps aux | grep -E "chat_core|web_server|judge|advisor" | grep -v grep | cut -c1-200 | head -8
