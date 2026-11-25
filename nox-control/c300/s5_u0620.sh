python3 - <<'P'
import json
a=json.load(open('/workspace/nox/web/site/qa/audit.json'))
for k in ('news','settings','atlas','photo','chat','index'):
    v=a.get(k,{}); print('OUT: ST',k,v.get('status'),v.get('wow'),v.get('ARU'),v.get('ts','')[11:16],'vend',len(v.get('vendor_used') or []),[ (f['item'][:25],str(f['detail'])[:70]) for f in v.get('fails',[])][:4])
import re
for k,v in a.items():
    raw=v.get('vision_raw') or ''
    m=re.search(r'"toporno"\s*:\s*\[(.*?)\]',raw,re.S)
    fx=v.get('fix') or []
    if v.get('ARU') and v['ARU'][2] is not None and v['ARU'][2]<=6:
        print('OUT: U',k,v['ARU'],'| toporno:',(m.group(1)[:260].replace('\n',' ') if m else ''),'| fix:',str(fx)[:260])
P
tail -c 120 /tmp/s5_chain.log | sed 's/^/OUT: tail /'; date +%H:%M
