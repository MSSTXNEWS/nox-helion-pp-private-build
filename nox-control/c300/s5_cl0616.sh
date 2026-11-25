grep -a " WOW " /tmp/s5_chain.log | cut -c1-400; tail -c 300 /tmp/s5_chain.log | grep -a CHAIN
python3 -c "
import json;a=json.load(open('/workspace/nox/web/site/qa/audit.json'))
for k in ('news','settings','atlas','photo','chat','index'):
    v=a.get(k,{}); print('OUT:',k,v.get('status'),v.get('wow'),v.get('ARU'),v.get('ts','')[11:16],'vend',v.get('vendor_used'),[ (f['item'][:30],str(f['detail'])[:90]) for f in v.get('fails',[])][:3])"
date +%H:%M
