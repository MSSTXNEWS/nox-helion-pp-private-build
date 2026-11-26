echo "C300: ch_ver1"
N=/workspace/nox; P=$N/svc/pipeline; cb=$(date +%s)
curl -fsSL --retry 5 --retry-all-errors "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_ui1/patch_ver.py?cb=$cb" -o /tmp/patch_ver.py || { echo FAIL; exit 0; }
cp $P/pipeline_svc.py $P/pipeline_svc.py.bak_ch_ver
python3 /tmp/patch_ver.py && python3 -m py_compile $P/pipeline_svc.py && echo pc_ok || { cp $P/pipeline_svc.py.bak_ch_ver $P/pipeline_svc.py; echo rollback; exit 0; }
grep -n "verified()" $P/pipeline_svc.py | cut -c1-200
pkill -f pipeline_svc.py; sleep 1; ( cd $P && nohup setsid $N/venv_living/bin/python pipeline_svc.py >$P/pipeline.log 2>&1 </dev/null & ); sleep 3; curl -s -m4 localhost:18217/health; echo
cat $N/state/ch_verified.json; echo
cb2=$(date +%s); curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/bundles/ch_ui1/q10.py?cb=$cb2" -o /tmp/q10.py
setsid -f python3 /tmp/q10.py b$cb2 > $N/state/ch_q10b.out 2>&1 < /dev/null; echo q10_started
