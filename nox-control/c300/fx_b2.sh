S=/workspace/nox/web/site
echo ==manual-tail; sed -n 80,200p $S/nox-manual.js | cut -c1-300
echo ==home; sed -n 1,40p $S/nox-p-home.js | cut -c1-900
echo ==minichat; sed -n 26,46p $S/nox-minichat.js | cut -c1-500
echo ==health; for u in /api/chat/health; do curl -s -m5 http://127.0.0.1:8091$u | head -c 700; echo; done
curl -s -m5 http://127.0.0.1:8090/health | head -c 900; echo
curl -s -m5 http://127.0.0.1:8200/v1/models | head -c 300; echo
grep -n "8200\|8104\|llama" /workspace/nox/web/pkg/server/web_server.py | head -5
for u in /api/nox-live /glm/v1/models /glm/v1/nox/stats; do echo $u; curl -s -m5 http://127.0.0.1:8091$u | head -c 300; echo; done
