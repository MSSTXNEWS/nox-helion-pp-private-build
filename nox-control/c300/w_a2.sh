echo "C300: w_a2"
S=/workspace/nox/web/site; N=/workspace/nox; cb=$(date +%s); R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
sleep 25
curl -fsSL --retry 5 --retry-all-errors "$R/w_a11y/nox-a11y-fix.js?cb=$cb" -o /tmp/a11y.js || { echo FAIL; exit 0; }
grep -q 'a11y-fix' /tmp/a11y.js || { echo STALE; exit 0; }
cp /tmp/a11y.js $S/nox-a11y-fix.js
n=0; for f in $S/*.html; do b=$(basename $f); case $b in index.html|index-legacy.html|*legacy*|chat-dc.html) continue;; esac
 grep -q 'nox-a11y-fix' $f && continue; grep -q '</body>' $f || continue
 python3 - "$f" <<'P'
import sys
p=sys.argv[1];s=open(p,encoding='utf-8').read()
i=s.rindex('</body>');s=s[:i]+'<script src="./nox-a11y-fix.js?v=1" defer></script>\n'+s[i:]
open(p,'w',encoding='utf-8').write(s)
P
 n=$((n+1)); done; echo patched $n
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$cb") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$cb") | tail -1
cmp $S/nox-a11y-fix.js $N/web/pkg/webroot/nox-a11y-fix.js && echo synced
curl -fsSL "$R/w_a11y/axe_scan.py?cb=$cb" -o /tmp/axe_scan.py
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
timeout 180 $N/venv/bin/python /tmp/axe_scan.py settings photo calendar 2>&1 | cut -c1-900
