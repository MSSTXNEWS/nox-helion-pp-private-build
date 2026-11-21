#!/bin/bash
a(){ iconv -f utf-8 -t ascii//TRANSLIT -c | cut -c1-200; }
S=/root/nox/state
echo "== train"; tail -n 2 /root/nox/logs/train_qwen9b_t131u.log | a; nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv,noheader
python3 - <<'PY'
import json,collections
for f in ['TASKS_1000_ACTIVATED.json','NOX_OPT_QUEUE_T168U.json','TASKS_1000_ACTIVATOR.json']:
    try:
        d=json.load(open('/root/nox/state/'+f))
    except Exception as e: print(f,'ERR',e); continue
    if isinstance(d,dict):
        print(f,'dict keys',list(d)[:10])
        for k,v in d.items():
            if isinstance(v,list): 
                print(' ',k,'list',len(v),'first',json.dumps(v[0],ensure_ascii=False)[:250] if v else '')
                if v and isinstance(v[0],dict): print('  status',collections.Counter(str(x.get('status')) for x in v).most_common(5))
            elif not isinstance(v,dict): print(' ',k,str(v)[:100])
    else: print(f,'list',len(d),json.dumps(d[0],ensure_ascii=False)[:250])
PY
echo "== activator proc"; ps aux | grep -i activator | grep -v grep | cut -c1-160
echo "== queue dirs"; ls /root/nox/state | grep -iE "inbox|queue|tasks" | head; ls /root/nox/tasks 2>/dev/null | head -5
