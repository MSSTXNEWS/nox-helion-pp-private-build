#!/bin/bash
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-230; }
for s in /root/nox/STOP /root/nox/STOP.flag /root/nox/state/STOP /root/nox/state/STOP.flag; do [ -e $s ] && { echo "STOP $s -> exit"; exit 0; }; done
Q=/root/nox/state/dispatcher/queue.jsonl; cp $Q $Q.bak_c63
python3 - <<'PY'
import json
d=json.load(open('/root/nox/tasks/1000_tasks_20261117.dispatcher.json'))['tasks']
seen=set()
for l in open('/root/nox/state/dispatcher/queue.jsonl'):
    try: seen.add(json.loads(l)['id'])
    except: pass
c=sorted([t for t in d if t['id'] not in seen],key=lambda t:(t.get('priority',9),t['id']))[:20]
with open('/root/nox/state/dispatcher/queue.jsonl','a') as f:
    for t in c:
        t=dict(t); t['status']='pending'; t['max_retries']=3; t['timeout_sec']=t.get('timeout_sec') or 1800
        f.write(json.dumps(t,ensure_ascii=False)+'\n')
print('appended',len(c),[t['id'] for t in c[:5]], 'handler',c[0].get('handler') if c else None)
PY
echo "== trainer batch vars"; grep -nE "environ|MICRO|MAX_LEN|MAXLEN|SEQ_LEN|per_device|grad_acc" /root/nox/scripts/train_qwen35_9b_t131u.py | head -14 | a
sleep 150
echo "== after 150s"; python3 - <<'PY'
import json,collections
s=json.load(open('/root/nox/state/dispatcher/state.json'))['tasks']
print(collections.Counter(t.get('status') for t in s.values()))
for k,t in list(s.items()):
    if k.startswith('t114u.00') and t.get('status') in('running','done','pending','claimed'): print(k,t.get('status'),t.get('claimed_by'),str(t.get('title'))[:50])
PY
