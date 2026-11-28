echo "K1: s6l_F3"
N=/workspace/nox; RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/s6l_files
curl -fsSL --retry 3 $RAW/persona_exam.py -o $N/mods/persona_exam.py
cd $N/mods && python3 -I persona_exam.py --score-keep $N/state/s6/exam_live.keep 2>&1 | cut -c1-260
echo END
