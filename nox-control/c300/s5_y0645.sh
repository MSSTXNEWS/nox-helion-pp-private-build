echo "OUT: $(tail -c 120 /tmp/s5_chain3.log | tr '\n' ' ')"
python3 - <<'P'
import json
a=json.load(open('/workspace/nox/web/site/qa/audit.json'))
for k in ('atlas','settings'):
    v=a.get(k,{}); print('OUT: ST',k,v.get('status'),v.get('wow'),v.get('ARU'),v.get('ts','')[11:16],'vend',v.get('vendor_used'),[(f['item'][:22],str(f['detail'])[:70]) for f in v.get('fails',[])][:5])
P
