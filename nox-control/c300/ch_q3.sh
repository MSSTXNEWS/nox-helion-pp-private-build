echo "C300: ch_q3"
N=/workspace/nox; cb=$(date +%s); R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_ui1
for f in pwq3.py fix5.css; do curl -fsSL "$R/$f?cb=$cb" -o /tmp/$f; done
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
for sz in "2559 950" "1920 1080"; do echo "== $sz fix"; timeout 80 $N/venv/bin/python /tmp/pwq3.py $sz fix 2>&1 | sed -n '1p;/B64BEGIN/,/B64END/p' | cut -c1-300; done
