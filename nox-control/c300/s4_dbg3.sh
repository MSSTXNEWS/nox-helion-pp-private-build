echo S4RUN:s4_dbg3
S=/workspace/nox/web/site
head -c 1200 $S/data/train_logs.json; echo; python3 -c "
import json;d=json.load(open('$S/data/train_logs.json'));print(type(d), list(d)[:12] if isinstance(d,dict) else len(d))"
tail -c 600 $S/data/organs_hist.jsonl
grep -n -i "train" $S/nox-brain-x.js | head -20 | cut -c1-220
cat /workspace/nox/state/*.json 2>/dev/null | head -c 600; ls /workspace/nox/state | head -20
