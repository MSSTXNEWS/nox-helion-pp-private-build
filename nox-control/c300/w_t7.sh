echo "C300: w_t7"
N=/workspace/nox; S=$N/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6 7 8; do t=$(date +%s)$k
 curl -fsSL "$R/w_tiles/nox-select-tiles.js?cb=$t" -o /tmp/tiles.js; curl -fsSL "$R/w_a11y/nox-a11y-fix.js?cb=$t" -o /tmp/a11y.js
 grep -q 'nxt' /tmp/tiles.js && grep -q 'textarea.m-wrap' /tmp/a11y.js && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
cp /tmp/tiles.js $S/nox-select-tiles.js; cp $S/nox-a11y-fix.js $S/nox-a11y-fix.js.bak_t7 2>/dev/null; cp /tmp/a11y.js $S/nox-a11y-fix.js
python3 - <<'P'
S='/workspace/nox/web/site/'
# system: fast/deep guard
f=S+'nox-p-system.js'; c=open(f).read(); o=c
c=c.replace("S.speed.fast.tps + ' ток/с'","((S.speed&&S.speed.fast&&S.speed.fast.tps!=null)?S.speed.fast.tps+' ток/с':'нет данных')").replace("S.speed.deep.tps + ' ток/с'","((S.speed.deep&&S.speed.deep.tps!=null)?S.speed.deep.tps+' ток/с':'нет данных')")
if c!=o: open(f+'.bak_t7','w').write(o); open(f,'w').write(c); print('system patched')
# tiles tag
for pg in ('voice.html','studio-legacy.html','settings.html'):
    try: h=open(S+pg).read()
    except Exception: print('no',pg); continue
    if 'nox-select-tiles.js' not in h:
        open(S+pg+'.bak_t7','w').write(h); open(S+pg,'w').write(h.replace('</body>','<script src="./nox-select-tiles.js?v=t1" defer></script></body>',1)); print('tiles',pg)
P
echo "--- routing (только строки маршрутов)"
CF=$N/ops/web_chat_auth/Caddyfile
grep -n '^\s*handle\|^\s*handle_path\|reverse_proxy' $CF | grep -i 'memory\|glm\|brain\|cmd\|data/live\|nox/status\|session\|:81\|:8[0-9][0-9][0-9]' | cut -c1-110 | head -40
for u in /memory/api /memory/health /glm/props /api/nox/status /web/api/nox/status /brain/intents /api/cmd /web/data/live.json /api/nox/session; do echo -n "$u -> "; curl -s -o /dev/null -w '%{http_code}\n' -m8 http://127.0.0.1:18091$u; done
echo -n "memory POST -> "; curl -s -o /dev/null -w '%{http_code}\n' -m10 -X POST -H 'content-type: application/json' -d '{"op":"core","budget_tokens":50}' http://127.0.0.1:18091/memory/api
ss -ltnp 2>/dev/null | grep -o '127.0.0.1:[0-9]*' | sort -u | tr '\n' ' '; echo
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
