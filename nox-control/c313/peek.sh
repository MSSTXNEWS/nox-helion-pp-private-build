#!/bin/bash
python3 - <<'P'
import json
d=json.load(open('/root/nox/state/flash2_suite_soul.json'))
for r in d['soul'][:12]:
    for s in r.get('steps',[])[:1]:
        print('##',r['id'],r.get('score'),[ (c['name'],c['score']) for c in s['checks']]); print('Q:',s['say'][:100]); a=s.get('answer',''); print('LEN',len(a)); print('A:',a[:200].replace('\n',' | ')); print('...',a[-100:].replace('\n',' | '))
P
