S=/workspace/nox/web/site
cd $S
[ -f x.txt ] && cp -p x.txt x.txt.bak_s1_$(date +%H%M%S)
base64 -d > x.txt <<'S1EOF'
eAo=
S1EOF
echo OK x.txt $(wc -c <x.txt)
cd /workspace/nox
wc -l web/pkg/server/chat_core.py web/pkg/server/web_server.py judges/judge_service.py
grep -n "^async def \|^def \|^class \|@app\.\(get\|post\)" judges/judge_service.py | head -30 | cut -c1-140
echo ==== chat_core
grep -n "^async def \|^def \|^class " web/pkg/server/chat_core.py | head -60 | cut -c1-140
grep -n "api/chat\|/api/turn\|8084\|8090" web/pkg/server/web_server.py | head -12 | cut -c1-200
