cd /workspace/nox/web/site
python3 - <<'P'
s=open('sw.js').read()
if "'push'" not in s:
    s+="self.addEventListener('push', (e) => { let d = {}; try { d = e.data ? e.data.json() : {}; } catch (x) { d = { body: e.data && e.data.text() }; } e.waitUntil(self.registration.showNotification(d.title || 'NOX HELION', { body: d.body || d.message || '', icon: './icons/icon-192.png', badge: './icons/icon-192.png', tag: d.tag })); });\n"
    open('sw.js','w').write(s)
P
echo ==ABS; grep -rnoE "(https?:)?//(127\.0\.0\.1|localhost|[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3})[:0-9]*[^'\"\` ]{0,40}" --include=*.js --include=*.html . 2>/dev/null | grep -v "bak_\|/vendor/\|/lib/\|/classic/\|w3.org" | head -20
echo ==PORTS; grep -rnE "fetch\(['\"\`]https?:" --include=*.js . 2>/dev/null | grep -v "bak_\|/vendor/\|/lib/" | cut -c1-140 | head
echo ==PS; ps -eo pid,etime,cmd | grep -E "web_server|nox_extra" | grep -v grep | cut -c1-140
grep -n "Basic\|WWW-Authenticate\|Authorization" /workspace/nox/web/pkg/server/web_server.py /workspace/nox/web/pkg/server/nox_extra.py 2>/dev/null | cut -c1-160 | head
echo ==CURL; for u in /api/chat/health /glm/v1/nox/stats /cal/events /api/nox/outbox /api/conv/x; do curl -s -m 20 -o /dev/null -w "$u %{http_code} %{time_total}\n" http://127.0.0.1:8091$u; done
curl -s -m 20 -X POST -H 'Content-Type: application/json' -d '{"conversation_id":"s1probe","message":"ответь одним словом: да","mode":"fast"}' http://127.0.0.1:8091/api/turn | head -c 600
