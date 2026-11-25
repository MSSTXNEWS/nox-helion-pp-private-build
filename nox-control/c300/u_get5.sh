echo "C300: u_get5"
python3 - <<'PYX'
import json
a=json.load(open('/workspace/nox/web/site/qa/audit.json',encoding='utf-8'))
d=a['creative'];print(d['ts']);print(d['vision_raw'][:1800]);print('FAILS',json.dumps(d['fails'],ensure_ascii=False)[:1500])
PYX
cat /workspace/nox/agent/out/u_qab_prog.txt | cut -c1-400
