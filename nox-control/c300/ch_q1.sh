echo "C300: ch_q1"
N=/workspace/nox; cb=$(date +%s)
curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_ui1/pwq.py?cb=$cb" -o /tmp/pwq.py
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright; timeout 100 $N/venv/bin/python /tmp/pwq.py 2>&1 | cut -c1-500
echo "== css nox-first"; grep -o "\.nox-first[^}]*}" $N/web/site/nox-*.css | cut -c1-300 | head -6
grep -ln "nox.ui.theme" $N/web/site/*.js | head; grep -n "ui.theme" $N/web/site/nox-theme.js | head -3
echo "== pkg webroot"; ls -d $N/web/pkg/webroot* $N/web/pkg/site* 2>/dev/null; ls $N/web/pkg | head -20; ls -l --time-style=+%H:%M $N/web/pkg/webroot/nox-chat-clean.css $N/web/pkg/webroot/nox-theme.js $N/web/pkg/webroot/sw.js 2>&1 | cut -c20-140
grep -n "webroot\|rsync\|cp .*site" $N/web/pkg/run_web.sh $N/web/run_web.sh $N/bin/run_web.sh 2>/dev/null | head -8 | cut -c1-200
