echo "C300: srv_k58"
cd /workspace/nox
/workspace/nox/venv/bin/python -I - <<'PY'
import json,glob
d=json.load(open('ops/dpo/gates_2079e42d0ab738d8.json'))
print({k:(v if not isinstance(v,(dict,list)) else '..') for k,v in d.items()})
print(d.get('reasons'))
def load(sha):
    fs=glob.glob('distill_v2/gates/%s-eval-*.json'%sha)+glob.glob('distill_v2/gates/%s.json'%sha)
    return fs
import os
base=d.get('base'); print('base',base)
for f in sorted(glob.glob('distill_v2/gates/*.json'),key=os.path.getmtime)[-6:]: print(os.path.basename(f)[:40], os.path.getsize(f))
for f in glob.glob('distill_v2/gates/2079e42d0ab738d8-eval-*.json'):
    e=json.load(open(f)); print('CAND fid',e['fid']['score'],e['fid']['by_cat']); print('soul',e['soul']['share'],'mb',e['mb']['overall'])
# база: ищем eval-отчёт по директории best_step_0075
for f in glob.glob('distill_v2/gates/*-eval-*.json'):
    e=json.load(open(f))
    if 'best_step_0075' in str(e.get('dir')):
        print('BASE0075',os.path.basename(f)[:20],e['fid']['score'],e['fid']['by_cat']); print('soul',e['soul']['share'],'mb',e['mb']['overall'])
PY
tail -n 3 agent/out/autotrain.log | cut -c1-160
