echo "C300: w_c7"
N=/workspace/nox; export PATH=$N/tools/node/bin:$PATH PLAYWRIGHT_BROWSERS_PATH=$N/tools/ms-playwright
sed 's#127.0.0.1:8091#127.0.0.1:18091#g' $N/tools/uiscore/score.py > $N/tools/uiscore/score18.py
rm -f $N/agent/out/ui_sc/index_*
timeout 250 $N/venv/bin/python $N/tools/uiscore/score18.py all index 2>&1 | tail -2
python3 $N/tools/uiscore/report.py 2>&1 | grep -E '^index ' | cut -c1-200
rm -f $N/tools/uiscore/score18.py
