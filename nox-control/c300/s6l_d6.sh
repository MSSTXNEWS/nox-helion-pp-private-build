echo "K1: s6l_d6"
N=/workspace/nox; S=$N/state/s6; RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300
pkill -f "persona_exam.py --chat" && echo "baseline exam stopped (chat protected)"; sleep 1
curl -fsSL --retry 3 $RAW/s6l_files/persona_exam.py -o $N/mods/persona_exam.py && echo "ok $(md5sum < $N/mods/persona_exam.py | cut -c1-8)"
cp $S/exam_base.keep $S/exam_base_snapshot.keep
python3 -I $N/mods/persona_exam.py --selftest
python3 -I $N/mods/persona_exam.py --score-keep $S/exam_base_snapshot.keep
echo END
