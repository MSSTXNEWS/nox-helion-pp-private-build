echo "C300: w_v6"
N=/workspace/nox; S=$N/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in $(seq 1 14); do t=$(date +%s)$k
 curl -fsSL "$R/ch_dc1/nox-dc-fix.js?cb=$t" -o /tmp/fix.js; curl -fsSL "$R/w_a11y/nox-a11y-fix.js?cb=$t" -o /tmp/a11y.js
 grep -q '#dcHead{background' /tmp/fix.js && grep -q 'st-pre>' /tmp/a11y.js && { ok=1; break; }; sleep 20; done
[ $ok = 1 ] || { echo STALE; exit 0; }
cp $S/nox-a11y-fix.js $S/nox-a11y-fix.js.bak_v6; cp /tmp/a11y.js $S/nox-a11y-fix.js; cp /tmp/fix.js $S/nox-dc-fix.js
python3 - <<'P'
S='/workspace/nox/web/site/'
f=S+'live.html'; h=open(f).read(); o="d.ts + ' UTC'"
if o in h: open(f+'.bak_v6','w').write(h); open(f,'w').write(h.replace(o,"(d.ts ? d.ts + ' UTC' : 'время: нет данных')")); print('live ts fixed')
f=S+'nox-dc.js'; h=open(f).read(); o='padding:clamp(24px,8vh,72px) 8px 8px'
if o in h: open(f+'.bak_v6','w').write(h); open(f,'w').write(h.replace(o,'padding:clamp(8px,3vh,28px) 8px 8px')); print('hero compact')
P
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
