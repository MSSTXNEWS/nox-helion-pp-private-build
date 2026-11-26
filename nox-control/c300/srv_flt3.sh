#!/bin/bash
D=/workspace/nox/distill_v2
python3 -I - <<'PY'
import json,collections,re
D="/workspace/nox/distill_v2"
T=collections.Counter(); S=collections.Counter(); K=collections.Counter()
for l in open(D+"/rows_train.jsonl",encoding="utf-8"):
    if not l.strip(): continue
    r=json.loads(l); T[re.sub(r"[:/].*","",str(r.get("teacher")))[:30]]+=1; S[str(r.get("source"))[:30]]+=1; K[str(r.get("kind"))[:30]]+=1
print("teachers",T.most_common(15)); print("sources",S.most_common(10)); print("kinds",K.most_common(10))
PY
grep -n -E "^def |^    def |ingest|rows_train" $D/code/distill_v2.py | grep -E "def (prep|ingest|cmd_|main|judge|gen)|ingest|rows_train" | cut -c1-170 | head -30
ls $D | grep -E "ready|pool|inject|skill" | head -20
ls /workspace/nox/state/p3/
