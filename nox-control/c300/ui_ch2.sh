echo "C300: ui_ch2 (чат v4: подписи системы, прогресс, миры, воздух)"
S=/workspace/nox/web/site; cd $S; TS=$(date +%s); mkdir -p /workspace/nox/web/ch_bak_$TS; cp -p chat-dc.html nox-dc.css nox-dc-cols.js /workspace/nox/web/ch_bak_$TS/
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_dc1
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; PY=/workspace/nox/venv/bin/python; export PATH=/workspace/nox/tools/node/bin:$PATH
for f in chat-dc.html nox-dc.css nox-dc-cols.js; do curl -fsSL --retry 5 --retry-all-errors $R/$f -o /tmp/$f && [ -s /tmp/$f ] || { echo FAIL $f; exit 0; }; done
node --check /tmp/nox-dc-cols.js || exit 0
cp /tmp/chat-dc.html /tmp/nox-dc.css /tmp/nox-dc-cols.js .
curl -fsSL --retry 5 https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/ui_ch1.sh | sed -n '/^cat > \/tmp\/chs.py/,$p' > /tmp/chs_run.sh; echo "echo; true" >> /tmp/chs_run.sh
sed -i "s/qa-ch1%d/qa-ch2%d/; s/B64 ch%d/B64 c2_%d/" /tmp/chs_run.sh
bash /tmp/chs_run.sh 2>&1 | cut -c1-3100
curl -fsSL --retry 5 https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/th_graphite/ensure.sh -o /tmp/th_ensure.sh && bash /tmp/th_ensure.sh 2>&1 | tail -2
