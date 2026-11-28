echo "K1: s6l_d4"
S=/workspace/nox/state/s6
python3 -I - <<'PY'
import json,collections
S="/workspace/nox/state/s6"
c=collections.Counter(); e=collections.Counter()
for l in open(S+"/exam_base.keep",encoding="utf-8"):
    r=json.loads(l); c[r["part"]]+=1
    if not r["answer"].strip(): e[r["part"]]+=1
print("answers",dict(c),"empty",dict(e))
PY
echo "proc=$(pgrep -f persona_exam.py | wc -l) open_proc=$(pgrep -f s6_open.py | wc -l)"; cat $S/persona_exam_base.log | tail -c 800
ls -la /workspace/nox/ops/dpo/pers1_open* 2>/dev/null | awk '{print $5,$9}'; tail -c 400 /workspace/nox/ops/dpo/s6_open.log
echo END
