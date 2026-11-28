echo "K1: s6l_h2"
S=/workspace/nox/state/s6
echo "running=$(pgrep -f 'persona_exam.py --chat' | wc -l) keep_lines=$(wc -l < $S/exam_live.keep)"
cat $S/persona_exam_live.log | tail -c 900
python3 -I /workspace/nox/mods/persona_exam.py --score-keep $S/exam_live.keep | cut -c1-500
echo END
