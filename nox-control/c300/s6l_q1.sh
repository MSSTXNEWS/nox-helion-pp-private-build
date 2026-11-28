echo "K1: s6l_q1"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; S=$N/state/s6; rm -f $S/exam_q30.keep
echo "running_prev=$(pgrep -f 'persona_exam.py --chat' | wc -l)"
setsid nohup nice -n 10 python3 -I $N/mods/persona_exam.py --chat http://127.0.0.1:18091 --keep $S/exam_q30.keep --out $S/persona_exam_q30.json > $S/persona_exam_q30.log 2>&1 < /dev/null &
echo started; echo END
