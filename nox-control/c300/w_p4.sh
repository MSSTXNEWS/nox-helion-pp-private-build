echo "C300: w_p4"
N=/workspace/nox
cat > /tmp/p4run.sh <<'R'
N=/workspace/nox; export PATH=$N/tools/node/bin:$PATH PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
cd $N/web/site
PAGES=$(ls *.html | sed 's/\.html$//' | grep -v -E '^(index-legacy|chat-dc)$' | tr '\n' ' ')
for pg in $PAGES; do
  [ -f $N/agent/out/ui_sc/${pg}_390_lh.json ] && [ $(find $N/agent/out/ui_sc/${pg}_390_lh.json -mmin -90 | wc -l) = 1 ] && continue
  timeout 150 $N/venv/bin/python $N/tools/uiscore/score.py own $pg 2>&1 | tail -1
done
echo ALLDONE
R
setsid -f bash /tmp/p4run.sh </dev/null >$N/agent/out/w_p4.log 2>&1
echo started; ls $N/web/site/*.html | wc -l
