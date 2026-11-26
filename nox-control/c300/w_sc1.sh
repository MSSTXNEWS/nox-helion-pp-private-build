echo "C300: w_sc1"
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; export PATH=/workspace/nox/tools/node/bin:$PATH
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ui_score
T=/workspace/nox/tools/uiscore; O=/workspace/nox/agent/out
curl -fsSL --retry 5 $R/report.py?cb=$(date +%s) -o $T/report.py
[ -d $O/ui_sc ] && python3 $T/report.py > $O/ui_report_before.txt 2>&1; tail -1 $O/ui_report_before.txt
mkdir -p $O/ui_sc_old; cp $O/ui_sc/*.json $O/ui_sc_old/ 2>/dev/null
rm -f $O/ui_sc/*.json $O/ui_sc.log
ALL=$(ls /workspace/nox/web/site/*.html | xargs -n1 basename | sed 's/\.html$//' | grep -v -E 'legacy|\.main$|^qa-|bak' | tr '\n' ' ')
echo "$ALL" | wc -w
sed -i 's/def lh(pgs,par=6)/def lh(pgs,par=3)/' $T/score.py
cat > /tmp/sc_run.sh <<B
export PLAYWRIGHT_BROWSERS_PATH=/workspace/nox/tools/ms-playwright; export PATH=/workspace/nox/tools/node/bin:\$PATH
T=$T; L=$O/ui_sc.log; PY=/workspace/nox/venv/bin/python
cd \$T
ALL="$ALL"
A="";B2="";C="";D="";i=0; for p in \$ALL; do case \$((i%4)) in 0) A="\$A \$p";; 1) B2="\$B2 \$p";; 2) C="\$C \$p";; 3) D="\$D \$p";; esac; i=\$((i+1)); done
for g in "\$A" "\$B2" "\$C" "\$D"; do \$PY \$T/score.py own \$g >> \$L 2>&1 & done; wait
echo "ALL OWN DONE" >> \$L
\$PY \$T/score.py lh \$ALL >> \$L 2>&1
echo "ALL LH DONE" >> \$L
B
setsid -f bash /tmp/sc_run.sh </dev/null >/dev/null 2>&1
sleep 3; echo started
