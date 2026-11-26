echo "C300: srv_k136"
cd /workspace/nox
sed -n 395,440p brain/DSP/test_dsp.py | cut -c1-170
echo "--- пути в тесте"; grep -n "ROOT\|tempfile\|/workspace\|mkdtemp\|NOX_ROOT\|def setUp" brain/DSP/test_dsp.py | head -20 | cut -c1-160
echo "--- train"; p=$(pgrep -f "distill_v2.py train" | head -1); tr '\0' ' ' </proc/$p/cmdline | cut -c1-300; echo; ps -o lstart= -p $p
cat state/tok_budget_max; ls -la --time-style=+%T state/tok_budget_max
grep -n "tok_budget\|preferred_budget" agent/autotrain/autotrain.sh distill_v2/code/distill_v2.py | head -10 | cut -c1-170
tail -n 3 agent/out/autotrain.log | cut -c1-200
