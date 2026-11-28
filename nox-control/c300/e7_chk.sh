echo "K1: e7_chk"; N=/workspace/nox
supervisorctl status nox_weekly_exam 2>&1 | head -2; tail -5 $N/logs/nox_weekly_exam.log 2>/dev/null | cut -c1-200
grep -n -B2 -A8 "nox_weekly_exam" /etc/supervisor/conf.d/*.conf 2>/dev/null | head -20; ls /etc/supervisor/conf.d 2>/dev/null | grep -i exam
grep -n "morning_brief_v5" $N/canon/canon.py | head -5 | cut -c1-240
cat $N/state/core/exam_run.out 2>/dev/null | cut -c1-400; echo END
