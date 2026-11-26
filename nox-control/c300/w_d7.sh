echo "C300: w_d7"
N=/workspace/nox; S=$N/web/site; V=$S/vendor/tabler-icons/icons/outline; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6 7 8; do t=$(date +%s)$k
 curl -fsSL "$R/w_a11y/nox-a11y-fix.js?cb=$t" -o /tmp/a11y.js; grep -q 'tb-burger,.nmc-x' /tmp/a11y.js && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
cp $S/nox-a11y-fix.js $S/nox-a11y-fix.js.bak_d7; cp /tmp/a11y.js $S/nox-a11y-fix.js
for p in "wand:wand-sparkles" "arrows-minimize:minimize-2" "microphone:mic" "text-spellcheck:spell-check"; do a=${p%%:*}; b=${p##*:}; [ -f $V/$b.svg ] || cp $V/$a.svg $V/$b.svg; ls -la $V/$b.svg | cut -c1-80; done
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
cmp $S/nox-a11y-fix.js $N/web/pkg/webroot/nox-a11y-fix.js && echo synced
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright PATH=$N/tools/node/bin:$PATH
for f in diag_page small_scan2; do curl -fsSL "$R/w_a11y/$f.py?cb=$(date +%s)" > /tmp/w18/$f.py 2>/dev/null || { mkdir -p /tmp/w18; curl -fsSL "$R/w_a11y/$f.py?cb=$(date +%s)" > /tmp/w18/$f.py; }; done
timeout 60 $N/venv/bin/python /tmp/w18/diag_page.py writer 2>&1 | cut -c1-200
timeout 100 $N/venv/bin/python /tmp/w18/small_scan2.py qa 2>&1 | cut -c1-500
for pg in qa writer; do rm -f $N/agent/out/ui_sc/${pg}_*; timeout 120 $N/venv/bin/python $N/tools/uiscore/score.py all $pg 2>&1 | tail -1; done
python3 $N/tools/uiscore/report.py 2>&1 | grep -E '^(qa|writer) ' | cut -c1-170
