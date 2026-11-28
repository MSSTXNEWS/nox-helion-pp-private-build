echo "K1: e7_res"; N=/workspace/nox
for i in $(seq 1 15); do [ -s $N/state/core/exam_run.out ] && break; sleep 10; done
cat $N/state/core/exam_run.out | cut -c1-420; pgrep -f "mods/weekly_exam.py" | head -2 | tr '\n' ' '; echo; tail -3 $N/state/core/exam_history.jsonl; cat $N/state/mind/exam_brief.json 2>/dev/null | cut -c1-300; echo; echo END
