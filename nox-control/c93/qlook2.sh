#!/bin/bash
cd /root/nox/state/dispatcher
python3 - <<'P'
import json,collections
q=[json.loads(l) for l in open('queue.jsonl') if l.strip()]
print(len(q),dict(collections.Counter(t.get('status') for t in q)))
for t in q:
    if t.get('status') in('pending','running','claimed'): print(t['id'],t.get('status'),t.get('class'),(t.get('title') or '')[:50])
P
echo == orders; wc -l owner_orders.jsonl owner_inbox.jsonl; tail -n 2 owner_orders.jsonl | cut -c1-700; echo == inbox; tail -n 2 owner_inbox.jsonl | cut -c1-700
grep -rlE "owner_inbox" /root/nox/scripts 2>/dev/null | head -5
