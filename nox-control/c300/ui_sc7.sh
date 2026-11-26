echo "C300: ui_sc7"
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; export PATH=/workspace/nox/tools/node/bin:$PATH
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ui_score
mkdir -p /workspace/nox/tools/uiscore /workspace/nox/agent/out/ui_sc; curl -fsSL --retry 5 $R/score.py -o /workspace/nox/tools/uiscore/score.py && curl -fsSL --retry 5 $R/report.py -o /workspace/nox/tools/uiscore/report.py || { echo FAIL; exit 0; }
rm -f /workspace/nox/agent/out/ui_sc/*.json /workspace/nox/agent/out/ui_sc.log
cat > /tmp/ui_sc_run.sh <<'B'
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; export PATH=/workspace/nox/tools/node/bin:$PATH
T=/workspace/nox/tools/uiscore; L=/workspace/nox/agent/out/ui_sc.log; PY=/workspace/nox/venv/bin/python
cd $T; [ -f package.json ] || npm init -y >/dev/null 2>&1
[ -f node_modules/axe-core/axe.min.js ] || npm i axe-core --no-audit --no-fund >> $L 2>&1
echo "axe ok $(ls node_modules/axe-core/axe.min.js)" >> $L
[ -x node_modules/.bin/lighthouse ] || npm i lighthouse --no-audit --no-fund >> $L 2>&1
echo "lh install: $(ls node_modules/.bin/lighthouse 2>&1)" >> $L
ALL="index creative settings system memory map knowledge widgets projects music news cinema mail calendar tools studio photo voice training dispatcher downloads board atlas pdf integrations assistant writer"
set -- $ALL; i=0; for p in $ALL; do case $((i%4)) in 0) A="$A $p";; 1) B2="$B2 $p";; 2) C="$C $p";; 3) D="$D $p";; esac; i=$((i+1)); done
for g in "$A" "$B2" "$C" "$D"; do $PY $T/score.py own $g >> $L 2>&1 & done; wait
echo "ALL OWN DONE" >> $L
$PY $T/score.py lh $ALL >> $L 2>&1
echo "ALL LH DONE" >> $L
B
setsid -f bash /tmp/ui_sc_run.sh </dev/null >/dev/null 2>&1
sleep 5; echo started
