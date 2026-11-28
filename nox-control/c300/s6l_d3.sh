echo "K1: s6l_d3"
export RUNNER_TRACKING_ID=""
N=/workspace/nox; RAW=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF:-main}/nox-control/c300; S=$N/state/s6; mkdir -p $S
for f in persona_guard.py persona_exam.py; do curl -fsSL --retry 3 $RAW/s6l_files/$f -o $N/mods/$f && echo "ok $f $(md5sum < $N/mods/$f | cut -c1-8)"; done
curl -fsSL --retry 3 $RAW/s6l_files/test_persona_guard.py -o $N/mods/tests/test_persona_guard.py
(cd $N/mods && python3 -I -m pytest -q tests/test_persona_guard.py 2>&1 | tail -1)
echo "open_proc=$(pgrep -f s6_open.py | wc -l) open_lines=$(wc -l < $N/ops/dpo/pers1_open.jsonl 2>/dev/null)"
for u in http://127.0.0.1:18091 http://127.0.0.1:8091; do c=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 $u/health); echo "$u health=$c"; done
CH=http://127.0.0.1:18091; [ "$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 $CH/health)" = 200 ] || CH=http://127.0.0.1:8091
rm -f $S/exam_base.keep
setsid nohup nice -n 10 python3 -I $N/mods/persona_exam.py --chat $CH --keep $S/exam_base.keep --out $S/persona_exam_base.json > $S/persona_exam_base.log 2>&1 < /dev/null &
sleep 30; ls -la $S | awk '{print $5,$9}'; tail -c 300 $S/persona_exam_base.log
echo END
