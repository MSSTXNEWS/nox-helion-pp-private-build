S=/workspace/nox/web/site
python3 - <<'P'
import json,collections
r=json.load(open('/workspace/nox/web/site/qa/report.json'))
print(r['bad'],r['total'])
g=collections.defaultdict(list)
for p,v in r['pages'].items():
    k=tuple(sorted(set(x.split(':')[0] if x.startswith('404') else x for x in v['desk']+v['mob'])))
    g[k].append(p)
for k,v in g.items(): print(k,len(v),v)
P
echo ==rework; for f in $S/qa/rework/*.json; do echo $f; cat $f; echo; done
echo ==qa_ctl; grep -n "верхн\|нижн\|canvas\|def \|selector\|querySelector" /workspace/nox/qa_ctl.py | head -50
echo ==nav; wc -c $S/nox-nav.js $S/nox-theme.js; grep -o "nox-[a-z-]*\(top\|bar\|dock\|header\|bottom\)[a-z-]*" $S/nox-nav.js | sort | uniq -c | sort -rn | head -15
echo ==advisors; head -45 $S/advisors.html
echo ==chat head; grep -n "<script\|<link" $S/chat.html | head -30
echo ==about; grep -n "<script\|<link" $S/about.html | head -30
echo ==api; curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8091/api/status; curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8091/music/health; ls /svc /svc/navidrome 2>&1|head; ss -ltnp | grep -E "8091|4533" | head
echo ==server; ps aux | grep -E "8091|serve|http" | grep -v grep | head -5
