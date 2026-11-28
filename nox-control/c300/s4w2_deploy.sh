N=/workspace/nox; RAW="https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/${REF}/nox-control/c300/s4w2_files"
echo "S4W2 $(date +%F_%H:%M)"
mkdir -p $N/mods/tests $N/ops/inj
for f in autonomy inj_exam iso_test foreign_mark; do curl -fsSL --retry 3 "$RAW/$f.py" -o $N/mods/$f.py || echo "FAIL $f"; done
for f in test_autonomy test_inj_exam test_foreign_mark; do curl -fsSL --retry 3 "$RAW/$f.py" -o $N/mods/tests/$f.py || echo "FAIL $f"; done
curl -fsSL --retry 3 "$RAW/build_inj_exam.py" -o $N/ops/dpo/build_inj_exam.py
cd $N/mods && python3 -I -m pytest -q tests/test_autonomy.py tests/test_inj_exam.py tests/test_foreign_mark.py 2>&1 | tail -2
python3 -I $N/ops/dpo/build_inj_exam.py 2>&1 | tail -6
echo "## detector on exam"; python3 -I $N/mods/inj_exam.py --detector | cut -c1-600
echo "## detector FP on other tests"
python3 -I - <<'PY'
import sys, collections
sys.path[:0]=["/workspace/nox/mods","/workspace/nox/brain/GROW/upgrade","/workspace/nox/brain/SLP","/workspace/nox/ops/dpo","/workspace/nox/ops"]
import foreign_mark as FM, soul_recognition as SR, ext_cases as EC
cc=collections.Counter(); tot=collections.Counter()
for c in EC.ext_cases(): tot[c["cat"]]+=1; cc[c["cat"]]+=FM.guard_user_message(c["prompt"])["flagged"]
print("ext", {k:"%d/%d"%(cc[k],tot[k]) for k in tot})
ids=[s["id"] for s in SR.SITUATIONS if s["id"].startswith("inj_")]
print("soul inj", sum(FM.guard_user_message(s["prompt"])["flagged"] for s in SR.SITUATIONS if s["id"] in ids),"/",len(ids))
fl=[s["id"] for s in SR.SITUATIONS if s["id"] not in ids and FM.guard_user_message(s["prompt"])["flagged"]]; print("soul other flagged", len(fl), fl)
PY
echo "## isolation"; python3 -I $N/mods/iso_test.py
