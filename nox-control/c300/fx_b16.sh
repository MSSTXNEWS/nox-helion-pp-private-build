S=/workspace/nox/web/site
date; tail -2 $S/qa/history.log; pgrep -af qa_ctl | head -3; head -c 300 /tmp/fx_qa.out
python3 - <<'P'
import json,collections
r=json.load(open('/workspace/nox/web/site/qa/report.json'));print(r['ts'],r['bad'],r['total'])
for p,v in r['pages'].items():
    if v['desk'] or v['mob']: print(p,'D',[x[:60] for x in v['desk']],'M',[x[:60] for x in v['mob']] if v['mob']!=v['desk'] else '=')
P
