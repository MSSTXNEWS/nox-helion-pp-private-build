#!/bin/bash
# c82: read-only: resource plan (dry-run) + disk report + почему dispatcher не берёт pending
B=https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/l1
echo "== resource_plan (dry-run)"; curl -fsSL $B/resource_plan.sh -o /tmp/rp.sh && bash /tmp/rp.sh 2>&1 | head -28
echo "== disk_report"; curl -fsSL $B/disk_report.sh -o /tmp/dr.sh && bash /tmp/dr.sh 2>&1 | head -22
echo "== dispatcher programs"; supervisorctl status 2>/dev/null | grep -iE "dispatch|sched|prior|worker|agent" | head -12
for f in $(ls -t /var/log/supervisor/*dispatch* /var/log/supervisor/*priority* 2>/dev/null | head -2); do echo "-- $f"; tail -n 8 "$f" | cut -c1-220; done
echo "== pending reasons"; python3 - <<'P'
import json,collections
q=[json.loads(l) for l in open('/root/nox/state/dispatcher/queue.jsonl') if l.strip()]
c=collections.Counter(); ex=[]
for t in q:
    if t.get('status')=='pending':
        c[(t.get('lane'),t.get('handler'),bool(t.get('deps')),str(t.get('next_try'))[:3])]+=1
        if len(ex)<3: ex.append({k:t.get(k) for k in ('id','lane','handler','deps','next_try','locks','class','attempts')})
print(c.most_common(6)); print(ex)
P
