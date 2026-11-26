#!/bin/bash
echo "C300: canon_probe5"
python3 - <<'PY'
import json
L=[l for l in open('/workspace/nox/state/mind/dream.jsonl') if l.strip()]
print('lines',len(L))
for l in L[-3:]:
    try:
        d=json.loads(l); print({k:(type(v).__name__,len(str(v))) for k,v in d.items()})
    except Exception as e: print('bad',type(e).__name__)
PY
