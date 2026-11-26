echo "C300: srv_k69"
cd /workspace/nox/ops/dpo
grep -a -A14 "Traceback" run2.log | cut -c1-220 | tail -n 18
/workspace/nox/venv/bin/python -I - <<'PY'
import json,glob
f=glob.glob('/workspace/nox/distill_v2/gates/*-eval-*.json'); 
e=[json.load(open(x)) for x in f]; e=[x for x in e if 'cand_dpo_11261135' in str(x.get('dir'))][0]
print('CAND2 fid',e['fid']['score'],e['fid']['by_cat']); print('soul',e['soul']['share'],'mb',e['mb']['overall'])
PY
