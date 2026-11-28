echo "K1: s6l_q2"
S=/workspace/nox/state/s6
echo "running=$(pgrep -f 'persona_exam.py --chat' | wc -l) keep_lines=$(wc -l < $S/exam_q30.keep)"
echo BEFORE; python3 -I /workspace/nox/mods/persona_exam.py --score-keep $S/exam_live.keep | cut -c1-400
echo AFTER; python3 -I /workspace/nox/mods/persona_exam.py --score-keep $S/exam_q30.keep | cut -c1-400
echo "lock=$([ -d /home/claude/brain/BODY_LOCK ] && echo yes || echo no) train=$(pgrep -f train_dpo.py | wc -l)"
echo END
