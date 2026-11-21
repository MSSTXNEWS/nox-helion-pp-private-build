#!/bin/bash
python3 - <<'P'
import json,collections
q=[json.loads(l) for l in open('/root/nox/state/dispatcher/queue.jsonl') if l.strip()]
print(len(q),collections.Counter(t.get('status') for t in q))
print(json.dumps(q[0],ensure_ascii=False)[:600])
for t in q[-2:]: print(json.dumps(t,ensure_ascii=False)[:500])
print("keys",sorted({k for t in q for k in t}))
P
ls /root/nox/state/dispatcher | head -30
