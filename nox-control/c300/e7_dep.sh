echo "K1: e7_dep"; export RUNNER_TRACKING_ID=""
N=/workspace/nox; R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles/pub; W=$(mktemp -d)
for f in weekly_exam.py ece_calc.py; do curl -fsSL "$R/$f?cb=$(date +%s)" -o $W/$f || { echo DL_FAIL $f; echo END; exit 0; }; python3 -m py_compile $W/$f || { echo COMPILE_FAIL $f; echo END; exit 0; }; done
cp -a $N/mods/weekly_exam.py $N/mods/weekly_exam.py.bak_e7 2>/dev/null; cp $W/weekly_exam.py $W/ece_calc.py $N/mods/; echo "installed md5=$(md5sum < $N/mods/weekly_exam.py | cut -c1-8)"
python3 -I $N/mods/ece_calc.py | cut -c1-200
supervisorctl restart nox_weekly_exam 2>&1 | tail -1
echo "brief writers:"; grep -rl "morning_brief_v5" $N --include=*.py --include=*.sh 2>/dev/null | grep -v -E "\.bak|archive|node_modules|api_bridge" | head -5
rm -f $N/state/core/exam_run.out; (setsid nohup nice -n 5 env NOX_ROOT=$N python3 -I $N/mods/weekly_exam.py > $N/state/core/exam_run.out 2>&1 &) ; sleep 2; echo "first run started"; echo END
