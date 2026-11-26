echo "C300: w_f4"
S=/workspace/nox/web/site; N=/workspace/nox; O=$N/agent/out; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles
ok=0; for k in 1 2 3 4 5 6 7 8; do t=$(date +%s)$k
 curl -fsSL "$R/w_a11y/nox-a11y-fix.js?cb=$t" -o /tmp/a11y.js; grep -q "nxl" /tmp/a11y.js && { ok=1; break; }; sleep 15; done
[ $ok = 1 ] || { echo STALE; exit 0; }
cp /tmp/a11y.js $S/nox-a11y-fix.js
bash <(curl -fsSL "$R/th_graphite/ensure.sh?cb=$(date +%s)") 2>&1 | tail -1; bash <(curl -fsSL "$R/th_graphite/webroot_sync.sh?cb=$(date +%s)") | tail -1
cmp $S/nox-a11y-fix.js $N/web/pkg/webroot/nox-a11y-fix.js && echo synced
wc -c $S/nox-theme.js
pkill -f 'score.py lh' ; pkill -f sc_run.sh; sleep 1
mkdir -p $O/ui_sc_lh_part; cp $O/ui_sc/*_lh.json $O/ui_sc_lh_part/ 2>/dev/null
rm -f $O/ui_sc/*_own.json
ALL=$(ls $S/*.html | xargs -n1 basename | sed 's/\.html$//' | grep -v -E 'legacy|\.main$|^qa-|bak' | tr '\n' ' ')
cat > /tmp/sc2_run.sh <<B
export PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright; export PATH=$N/tools/node/bin:\$PATH
T=$N/tools/uiscore; L=$O/ui_sc2.log; PY=$N/venv/bin/python; cd \$T
ALL="$ALL"
A="";B2="";C="";D="";i=0; for p in \$ALL; do case \$((i%4)) in 0) A="\$A \$p";; 1) B2="\$B2 \$p";; 2) C="\$C \$p";; 3) D="\$D \$p";; esac; i=\$((i+1)); done
for g in "\$A" "\$B2" "\$C" "\$D"; do \$PY \$T/score.py own \$g >> \$L 2>&1 & done; wait
echo "ALL OWN DONE" >> \$L
\$PY \$T/score.py lh index chat-dc settings system memory music calendar photo studio writer tv voice map mail knowledge >> \$L 2>&1
echo "ALL LH DONE" >> \$L
B
rm -f $O/ui_sc2.log; setsid -f bash /tmp/sc2_run.sh </dev/null >/dev/null 2>&1; sleep 2; echo started
