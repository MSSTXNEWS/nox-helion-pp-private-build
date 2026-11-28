echo "K1: e7_dep2"; export RUNNER_TRACKING_ID=""; N=/workspace/nox
R=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300/bundles/pub; W=$(mktemp -d)
for f in weekly_exam.py persona_exam.py persona_guard.py; do curl -fsSL "$R/$f?cb=$(date +%s)" -o $W/$f && python3 -m py_compile $W/$f || { echo DL_FAIL $f; echo END; exit 0; }; done
cp -a $N/mods/weekly_exam.py $N/mods/weekly_exam.py.bak_e7b; cp $W/weekly_exam.py $N/mods/
for f in persona_exam.py persona_guard.py; do [ -e $N/mods/$f ] && echo "$f exists md5=$(md5sum < $N/mods/$f | cut -c1-8) pub=$(md5sum < $W/$f | cut -c1-8)" || { cp $W/$f $N/mods/; echo "$f installed"; }; done
echo "set=$([ -s $N/ops/persona/persona_exam_set.json ] && echo 1 || echo 0) inj2_eval=$(wc -l < $N/ops/dpo/dpo_inj2_eval.jsonl 2>/dev/null) soul_recog=$(find $N/brain/GROW/upgrade -name soul_recognition.py 2>/dev/null | wc -l)"
python3 -I $N/mods/persona_exam.py --selftest 2>&1 | tail -1
supervisorctl restart nox_weekly_exam 2>&1 | tail -1
python3 -I - <<'PY'
import sys; sys.path.insert(0,"/workspace/nox/mods"); import weekly_exam as w
r=w.turn("qa-exam-pre","Скажи одно слово.",timeout=60); print("chat busy=%s ok=%s ttft=%s"%(r["busy"],r["ok"],r["ttft"] and round(r["ttft"],2)))
PY
echo "gpu: $(nvidia-smi --query-gpu=memory.used,utilization.gpu --format=csv,noheader 2>/dev/null)"; ls $N/state/body_lock BODY_LOCK /home/claude/brain/BODY_LOCK 2>/dev/null | head -2
echo END
