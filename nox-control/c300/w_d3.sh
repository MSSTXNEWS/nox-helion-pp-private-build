echo "C300: w_d3"
N=/workspace/nox
cat > /tmp/d3run.sh <<'R'
N=/workspace/nox; export PATH=$N/tools/node/bin:$PATH PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
for pg in qa live studio tv settings system memory writer chat chat-dc calendar photo board about advisors ai-learning assistant atlas benchmark book-reader browser; do
  rm -f $N/agent/out/ui_sc/${pg}_*
  timeout 200 $N/venv/bin/python $N/tools/uiscore/score.py all $pg 2>&1 | tail -1
done
echo ALLDONE
R
setsid -f bash /tmp/d3run.sh </dev/null >$N/agent/out/w_d3.log 2>&1
echo started
