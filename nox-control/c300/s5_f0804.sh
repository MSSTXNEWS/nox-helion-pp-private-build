python3 - <<'P'
import json,re
a=json.load(open('/workspace/nox/web/site/qa/audit.json'))
for k in ('atlas','finance'):
    v=a.get(k,{}); raw=v.get('vision_raw') or ''
    t=re.search(r'"toporno"\s*:\s*\[(.*?)\]',raw,re.S); p=re.search(r'"patterns_missing"\s*:\s*\[(.*?)\]',raw,re.S)
    print('OUT:',k,'fix:',str(v.get('fix'))[:420],'| top:',(t.group(1)[:300] if t else ''),'| miss:',(p.group(1)[:300] if p else ''))
P
tail -c 150 /tmp/s5_chain4.log | tr '\n' ' ' | sed 's/^/OUT: /'
