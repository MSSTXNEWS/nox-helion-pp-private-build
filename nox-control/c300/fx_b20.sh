S=/workspace/nox/web/site
date; tail -2 $S/qa/history.log
python3 - <<'P'
import json
r=json.load(open('/workspace/nox/web/site/qa/report.json'));print(r['ts'],r['bad'],r['total'])
for p,v in r['pages'].items():
    if v['desk'] or v['mob']: print(p,'D',[x[:90] for x in v['desk']],'M',[x[:90] for x in v['mob']] if v['mob']!=v['desk'] else '=')
a=json.load(open('/workspace/nox/web/site/qa/audit.json'))
for k,v in a.items(): print(k,v.get('ts'),v.get('status'),[ (f['item'][:30]) for f in v.get('fails',[])])
P
