echo "C300: ch_dc1"
S=/workspace/nox/web/site; N=/workspace/nox; cb=$(date +%s); R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_dc1
for f in chat-dc.html nox-dc.css nox-dc.js pwdc.py; do curl -fsSL --retry 5 --retry-all-errors "$R/$f?cb=$cb" -o /tmp/dc_$f || { echo FAIL $f; exit 0; }; done
grep -q "history=cur.msgs" /tmp/dc_nox-dc.js || { echo STALE; exit 0; }
echo "theme size: $(wc -c < $S/nox-theme.js) pkg: $(wc -c < $N/web/pkg/webroot/nox-theme.js)"
[ -f $S/chat.html.bak_ch_dc ] || cp $S/chat.html $S/chat.html.bak_ch_dc
cp /tmp/dc_chat-dc.html $S/chat-dc.html; cp /tmp/dc_nox-dc.css $S/nox-dc.css; cp /tmp/dc_nox-dc.js $S/nox-dc.js
grep -q "CH-DC" $S/chat.html || python3 - <<'PY'
p='/workspace/nox/web/site/chat.html'
s=open(p).read()
snip='<script>/*CH-DC*/if(!/[?&]legacy=1/.test(location.search)&&!/[?&]dc=0/.test(location.search))location.replace("chat-dc.html"+location.search+location.hash)</script>'
i=s.find('<head>')
s=s[:i+6]+snip+s[i+6:] if i>=0 else snip+s
open(p,'w').write(s)
PY
grep -c "CH-DC" $S/chat.html
bash <(curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/th_graphite/webroot_sync.sh?cb=$cb")
for f in chat.html chat-dc.html nox-dc.css nox-dc.js; do cmp $S/$f $N/web/pkg/webroot/$f && echo synced_$f; done
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
ss -ltnp 2>/dev/null | grep -o ":80[0-9][0-9]" | sort -u | tr '\n' ' '
curl -s -o /dev/null -w "web80:%{http_code}\n" http://127.0.0.1:8080/web/chat.html
NOXPORT=8080 timeout 200 $N/venv/bin/python /tmp/dc_pwdc.py 2>&1 | grep -v B64 | cut -c1-400
