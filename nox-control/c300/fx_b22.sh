S=/workspace/nox/web/site
python3 - <<'P'
import json
r=json.load(open('/workspace/nox/web/site/qa/report.json'));print(r['ts'],r['bad'],r['total'])
for p,v in r['pages'].items():
    if v['desk'] or v['mob']: print(p,'D',[x[:110] for x in v['desk']],'M',[x[:110] for x in v['mob']] if v['mob']!=v['desk'] else '=')
P
grep -rn "i_['\"]" $S/studio.html $S/nox-*.js 2>/dev/null | cut -c1-220 | head -5
grep -n "<script" $S/studio.html | cut -c1-160
