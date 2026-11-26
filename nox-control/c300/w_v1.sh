echo "C300: w_v1"
N=/workspace/nox; S=$N/web/site; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6; do t=$(date +%s)$k
 for f in w_v1/nox-w2-fix.js w_v1/nox-unload-shim.js w_u1/nox-t44.js; do curl -fsSL "$R/$f?cb=$t" -o /tmp/v_$(basename $f); done
 grep -q 'Transition was aborted' /tmp/v_nox-w2-fix.js && grep -q pagehide /tmp/v_nox-unload-shim.js && grep -q 'studio|voice' /tmp/v_nox-t44.js && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
cp /tmp/v_nox-w2-fix.js $S/nox-w2-fix.js; cp /tmp/v_nox-unload-shim.js $S/nox-unload-shim.js; cp $S/nox-t44.js $S/nox-t44.js.bak_v1; cp /tmp/v_nox-t44.js $S/nox-t44.js
python3 - <<'P'
S='/workspace/nox/web/site/'
def tag(pg,js,first=False):
    try: h=open(S+pg).read()
    except Exception: print('no',pg); return
    if js in h: return
    open(S+pg+'.bak_v1','w').write(h)
    t='<script src="./%s?v=v1"%s></script>'%(js,'' if first else ' defer')
    if first and '<head>' in h: h=h.replace('<head>','<head>'+t,1)
    else: h=h.replace('</body>',t+'</body>',1)
    open(S+pg,'w').write(h); print('tag',pg,js)
for pg in ('board.html','scene.html'): tag(pg,'nox-unload-shim.js',True)
for pg in ('cinema.html','board.html','scene.html','studio.html','studio-legacy.html','voice.html','intents.html','calendar.html','photo.html'): tag(pg,'nox-w2-fix.js')
for pg in ('studio.html','studio-legacy.html','voice.html','scene.html','board.html','calendar.html','photo.html','settings.html'): tag(pg,'nox-t44.js')
tag('studio-legacy.html','nox-select-tiles.js')
P
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
echo "- WEB w_v1 (26.11): ACCEPT пачка 2: unload-shim (board/scene), Transition-aborted guard, битые превью (cinema), слой 44 px на studio/voice/scene/board/calendar/photo/settings (?w2=0 ?t44=0)" >> /dev/null
