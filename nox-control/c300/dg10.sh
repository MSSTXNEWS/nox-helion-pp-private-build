echo "K1: dg10 (read-only, CPU)"; N=/workspace/nox; V=$N/distill_v2
echo "hold files:"; ls -l --time-style=+%m%d-%H:%M $V/hold*.jsonl $V/*hold* 2>/dev/null | awk '{print $5,$6,$7}' | sed 's#/workspace/nox/##'
echo "sha_hold=$(sha256sum $V/hold_frozen_v1.jsonl | cut -c1-8) rows=$(wc -l < $V/hold_frozen_v1.jsonl)"
python3 - <<'PY'
import json,collections
V="/workspace/nox/distill_v2/hold_frozen_v1.jsonl"
rows=[json.loads(l) for l in open(V,encoding="utf-8") if l.strip()]
print("keys",sorted(rows[0].keys()))
L=[len(r["ids"]) for r in rows]; print("len min/med/max",min(L),sorted(L)[len(L)//2],max(L))
ks=[str(r["key"]) for r in rows]; print("key sample",[k[:14] for k in ks[:3]],"prefix_counts",collections.Counter(k.split(":")[0][:10] for k in ks).most_common(6))
print("labels masked share",round(sum(sum(1 for x in r["labels"] if x==-100) for r in rows)/sum(L),3))
PY
echo "--- who builds/uses hold_frozen"; grep -rlE "hold_frozen" $V/code $N/ops $N/agent --include=*.py --include=*.sh 2>/dev/null | head -12 | sed 's#/workspace/nox/##'
grep -nE "hold_frozen|hold_fp|HOLD_FP|def .*hold" $V/code/distill_v2.py 2>/dev/null | cut -c1-150 | head -14
echo "--- training data pools in distill_v2"; ls $V | head -40 | tr '\n' ' '; echo
ls -l --time-style=+%m%d $V/*.jsonl 2>/dev/null | awk '{print $5,$7}' | head -20 | tr '\n' ';'; echo
echo "--- hold fp refs: $(grep -rhoE '21772a97593e[:0-9]*' $N/agent/out/ckpt_best_global.json 2>/dev/null | head -2 | tr '\n' ' ')"
echo END
