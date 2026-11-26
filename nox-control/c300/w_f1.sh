echo "C300: w_f1"
S=/workspace/nox/web/site; N=/workspace/nox; cb=$(date +%s); R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
sleep 25
curl -fsSL --retry 5 --retry-all-errors "$R/w_frame/nox-frame.js?cb=$cb" -o /tmp/nxf.js || { echo FAIL; exit 0; }
grep -q 'NOX frame' /tmp/nxf.js || { echo STALE; exit 0; }
cp /tmp/nxf.js $S/nox-frame.js
n=0; for b in advisors ai-learning atlas browser calls connections contacts editor evolution forge g01-status g02-owner g03-release g04-provider g05-evidence g06-orchestrator g07-hardware games knowledge mail marketing messenger mini operators ops pc-control pc-maintenance pdf social spaces tv weights ; do f=$S/$b.html; [ -f $f ] || continue; grep -q 'nox-frame.js' $f && continue; grep -q 'class="wrap"' $f || continue
python3 - "$f" <<'P'
import sys
p=sys.argv[1];s=open(p,encoding='utf-8').read()
i=s.rindex('</body>');s=s[:i]+'<script src="./nox-frame.js?v=1" defer></script>\n'+s[i:]
open(p,'w',encoding='utf-8').write(s)
P
n=$((n+1)); echo -n "$b "; done; echo; echo patched $n
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$cb") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$cb") | tail -1
cmp $S/nox-frame.js $N/web/pkg/webroot/nox-frame.js && echo synced
curl -fsSL "$R/w_a11y/axe_scan.py?cb=$cb" -o /tmp/axe_scan.py
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
timeout 150 $N/venv/bin/python /tmp/axe_scan.py advisors contacts mail 2>&1 | cut -c1-500
grep -E 'VISION' $N/agent/out/dcqa.out | cut -c1-300
