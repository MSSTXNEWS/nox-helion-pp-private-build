echo "C300: w_i3"
S=/workspace/nox/web/site; N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6 7 8; do t=$(date +%s)$k
 curl -fsSL "$R/w_photo/nox-photo-dc.js?cb=$t" -o /tmp/pdc.js; curl -fsSL "$R/w_index/nox-index-fix.js?cb=$t" -o /tmp/ixf.js; curl -fsSL "$R/ui_score/score.py?cb=$t" -o /tmp/score.py
 grep -q 'deep-chat' /tmp/pdc.js && grep -q 'ixfix' /tmp/ixf.js && grep -q swiftshader /tmp/score.py && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
cp /tmp/pdc.js $S/nox-photo-dc.js; cp /tmp/ixf.js $S/nox-index-fix.js; cp /tmp/score.py $N/tools/uiscore/score.py; sed -i 's/def lh(pgs,par=6)/def lh(pgs,par=3)/' $N/tools/uiscore/score.py
python3 - <<'P'
S='/workspace/nox/web/site/'
def rw(n,f):
    p=S+n;s=open(p,encoding='utf-8').read();t=f(s)
    if t!=s:
        import shutil;shutil.copy(p,p+'.bak_w_i3');open(p,'w',encoding='utf-8').write(t);print('patched',n)
    else: print('skip',n)
def photo(s):
    if 'nox-photo-dc' in s: return s
    i=s.rindex('</body>');return s[:i]+'<script src="./nox-photo-dc.js?v=1" defer></script>\n'+s[i:]
def index(s):
    if 'nox-index-fix' in s: return s
    j=s.index('>',s.index('<meta charset'))+1;return s[:j]+'\n<script src="./nox-index-fix.js?v=1"></script>'+s[j:]
def tv(s):
    for u in ['./nox-worlds.js','./vendor/nox-x/reveal/reveal.js','./vendor/nox-x/reveal/markdown.js']:
        a='<script src="%s"></script>'%u
        if a in s: s=s.replace(a,'<script src="%s" defer></script>'%u)
    return s
rw('photo.html',photo);rw('index.html',index);rw('tv.html',tv)
P
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
for f in photo.html index.html tv.html nox-photo-dc.js nox-index-fix.js; do cmp $S/$f $N/web/pkg/webroot/$f && echo synced_$f; done
curl -fsSL "$R/w_a11y/axe_scan.py?cb=$(date +%s)" -o /tmp/axe_scan.py; curl -fsSL "$R/w_a11y/diag_page.py?cb=$(date +%s)" -o /tmp/diag_page.py
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
timeout 120 $N/venv/bin/python /tmp/axe_scan.py index photo 2>&1 | cut -c1-500
timeout 60 $N/venv/bin/python /tmp/diag_page.py index 2>&1 | cut -c1-360
