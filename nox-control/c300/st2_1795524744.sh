cp /workspace/nox/qa_audit.py /workspace/nox/qa_audit.py.bak_cyc
curl -fsSL "https://raw.githubusercontent.com/MSSTXNEWS/nox-helion-pp-private-build/main/nox-control/c300/qa_audit.py?c=$RANDOM" -o /workspace/nox/qa_audit.py
python3 -m py_compile /workspace/nox/qa_audit.py && echo compiled
python3 - <<'P'
import json;p='/workspace/nox/web/site/qa/audit.json';d=json.load(open(p))
for v in d.values():
  if v['status']=='owner': v['status']='rework'; v['cycle']=0
json.dump(d,open(p,'w'),ensure_ascii=False,indent=1);print('reset',len(d))
P
