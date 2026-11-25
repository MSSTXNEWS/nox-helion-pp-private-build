echo "C300: k2_p4"
S=/workspace/nox/web/site
python3 - <<'PY'
import json
r=json.load(open('/workspace/nox/web/site/qa/registry.json'))
for s in r['sections'].values():
    pass
def walk(o,p=''):
    if isinstance(o,dict):
        for k,v in o.items():
            if 'chat.send' in k or k=='chat.send': print(p,k,json.dumps(v,ensure_ascii=False)[:300])
            walk(v,p+'/'+k)
    elif isinstance(o,list):
        for x in o: walk(x,p)
walk(r)
print([k for k in r.keys()])
c=r.get('commands')
print(type(c), (list(c)[:5] if c else None))
PY
grep -n "chat.send" $S/nox-actions.js $S/nox-cmd.js | cut -c1-260 | head -6
grep -o 'class="[^"]*card[^"]*"' $S/index.html | sort | uniq -c | sort -rn | head -5
grep -n "</body>" $S/index.html | head -2
ls $S/qa/rework | grep -c fixed
cat $S/qa/rework/calendar.fixed | tail -2
exit 0
