cd /workspace/nox/web/site; sed -n '35,75p' nox-photo.js | cut -c1-700; grep -n "gM\b\|id=\"gM\"" photo.html | cut -c1-500 | head -3
curl -s -m 5 127.0.0.1:8091/img/health | head -c 100
grep -n "_c300_img_file" -A12 /workspace/nox/web/pkg/server/web_server.py | head -30 | cut -c1-200
