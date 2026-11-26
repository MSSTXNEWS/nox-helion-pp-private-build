echo "C300: w_f5"
S=/workspace/nox/web/site; N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6 7 8; do t=$(date +%s)$k
 curl -fsSL "$R/w_a11y/nox-a11y-fix.js?cb=$t" -o /tmp/a11y.js; grep -q 'h3\[role\]' /tmp/a11y.js && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
cp /tmp/a11y.js $S/nox-a11y-fix.js
python3 - <<'P'
import glob,os
S='/workspace/nox/web/site/';n=0;m=[]
for f in sorted(glob.glob(S+'*.html')):
    b=os.path.basename(f)
    if b in('index.html','chat-dc.html') or 'legacy' in b or b.endswith('.main.html') or b.startswith('qa-') or 'bak' in b: continue
    s=open(f,encoding='utf-8',errors='replace').read();ch=0
    if 'nox-a11y-fix' not in s and '</body>' in s:
        i=s.rindex('</body>');s=s[:i]+'<script src="./nox-a11y-fix.js?v=1" defer></script>\n'+s[i:];ch=1;m.append(b+':a11y')
    if b=='live.html' and 'nox-theme.js' not in s and '</head>' in s:
        s=s.replace('</head>','<script src="./nox-theme.js"></script>\n</head>',1);ch=1;m.append('live:theme')
    if ch: open(f,'w',encoding='utf-8').write(s);n+=1
print('patched',n,m)
P
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
cmp $S/live.html $N/web/pkg/webroot/live.html && echo synced_live
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
curl -fsSL "$R/w_a11y/axe_scan.py?cb=$(date +%s)" -o /tmp/axe_scan.py
timeout 200 $N/venv/bin/python /tmp/axe_scan.py photo live tv 2>&1 | cut -c1-500
