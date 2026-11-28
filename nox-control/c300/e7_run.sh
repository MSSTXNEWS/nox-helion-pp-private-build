echo "K1: e7_run"; export RUNNER_TRACKING_ID=""; N=/workspace/nox
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles/pub; W=$(mktemp -d)
curl -fsSL "$R/weekly_exam.py?cb=$(date +%s)" -o $W/w.py && python3 -m py_compile $W/w.py || { echo DL_FAIL; echo END; exit 0; }
cp $W/w.py $N/mods/weekly_exam.py; echo "md5=$(md5sum < $N/mods/weekly_exam.py | cut -c1-8)"; supervisorctl restart nox_weekly_exam 2>&1 | tail -1
rm -f $N/state/core/exam_run.out; (setsid nohup nice -n 5 env NOX_ROOT=$N python3 -I $N/mods/weekly_exam.py > $N/state/core/exam_run.out 2>&1 &)
for i in $(seq 1 16); do sleep 10; grep -q "^13 " $N/state/core/exam_run.out 2>/dev/null && break; done
cut -c1-420 $N/state/core/exam_run.out; echo END
