echo "C300: w_f2"
S=/workspace/nox/web/site; N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6 7 8; do t=$(date +%s)$k
 curl -fsSL "$R/w_tv/nox-tv-player.js?cb=$t" -o /tmp/tvp.js; curl -fsSL "$R/w_frame/nox-frame.js?cb=$t" -o /tmp/nxf.js; curl -fsSL "$R/w_a11y/nox-a11y-fix.js?cb=$t" -o /tmp/a11y.js
 grep -q '__nxHls' /tmp/tvp.js && grep -q 'operators/.test(location.pathname)){' /tmp/nxf.js && grep -q 'data-page=tv' /tmp/a11y.js && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
cp /tmp/tvp.js $S/nox-tv-player.js; cp /tmp/nxf.js $S/nox-frame.js; cp /tmp/a11y.js $S/nox-a11y-fix.js
python3 - <<'P'
S='/workspace/nox/web/site/'
s=open(S+'operators.html',encoding='utf-8').read()
if 'nox-frame' not in s and '</body>' in s:
    i=s.rindex('</body>');open(S+'operators.html','w',encoding='utf-8').write(s[:i]+'<script src="./nox-frame.js?v=2" defer></script>\n'+s[i:]);print('operators patched')
else: print('operators skip')
P
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
for f in operators.html nox-frame.js nox-tv-player.js nox-a11y-fix.js; do cmp $S/$f $N/web/pkg/webroot/$f && echo synced_$f; done
tail -3 $N/agent/out/ui_sc.log | cut -c1-150
