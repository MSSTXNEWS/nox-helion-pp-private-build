#!/bin/bash
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-190; }
echo "== dispatcher log tail"; tail -14 /root/nox/logs/dispatcher_t855u.log | a
echo "== MODES"; grep -n -A6 "^MODES" /root/nox/scripts/owner_autonomy_pool.py | a
echo "== dispatcher conf location"; grep -rl "nox_dispatcher_t855u" /etc/supervisor /opt/supervisor-scripts 2>/dev/null | head -3
echo "== STOP flags"; ls /root/nox/state | grep -iE "^STOP|SAFE70|PAUSE|HOLD" | head; ls /root/nox | grep -iE "^STOP" | head -3
echo "== autonomy state (full keys)"; python3 -c "import json;d=json.load(open('/root/nox/state/owner_autonomy_mode_v15.json'));print({k:(str(v)[:60]) for k,v in d.items()})" 2>&1 | a
echo "== pending reasons"; python3 - <<'PY' 2>&1 | a
import json
rows=[json.loads(l) for l in open('/root/nox/state/dispatcher/queue.jsonl') if l.strip()] if __import__('os').path.exists('/root/nox/state/dispatcher/queue.jsonl') else []
from collections import Counter
print(len(rows), Counter(r.get('status') for r in rows).most_common(6))
print([ (r.get('id') or r.get('task_id'), r.get('status'), str(r.get('blocked_by') or r.get('reason') or '')[:40]) for r in rows if r.get('status') in ('pending','ready','blocked')][:6])
PY
